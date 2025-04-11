"""
Piyasa verilerini yönetir ve analiz eder
"""

import time
import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

import pandas as pd
import random
from ta.trend import MACD, ADXIndicator, EMAIndicator, IchimokuIndicator, SMAIndicator
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands, AverageTrueRange, KeltnerChannel
from ta.volume import OnBalanceVolumeIndicator, VolumePriceTrendIndicator

from trading_bot.api.binance_client import BinanceClient
from trading_bot.core.strategy import StrategyParams

logger = logging.getLogger("trading_bot")

class DynamicTargetPool:
    """Dinamik olarak önceliklendirilmiş sembol havuzunu yönetir."""
    
    def __init__(self, max_pool_size=50):
        """
        Dinamik hedef havuzu başlatır.
        
        Args:
            max_pool_size (int): Havuzda tutulacak maksimum sembol sayısı
        """
        self.targets = {}  # {symbol: {'score': float, 'last_check': timestamp, 'signal_strength': float, ...}}
        self.max_pool_size = max_pool_size
        self.lock = asyncio.Lock()  # Eşzamanlı erişim için kilit
        self.last_full_refresh = 0  # Son tam yenileme zamanı
        self.attempt_failures = {}  # {symbol: {'count': int, 'last_failure': timestamp}}
        self.success_history = {}   # {symbol: {'count': int, 'last_success': timestamp}}
    
    async def add_or_update_target(self, symbol: str, data: Dict):
        """
        Sembolü havuza ekler veya günceller.
        
        Args:
            symbol (str): Eklenecek/güncellenecek sembol
            data (Dict): Sembolle ilgili veriler (puanlar, sinyal gücü, vb.)
        """
        async with self.lock:
            current_time = time.time()
            
            if symbol in self.targets:
                # Mevcut hedefi güncelle
                self.targets[symbol].update(data)
                self.targets[symbol]['last_update'] = current_time
            else:
                # Yeni hedef ekle
                self.targets[symbol] = data
                self.targets[symbol]['last_update'] = current_time
            
            # Havuzu maksimum boyuta sınırla - en düşük puanlı sembolleri kaldır
            if len(self.targets) > self.max_pool_size:
                sorted_targets = sorted(self.targets.items(), key=lambda x: x[1].get('score', 0))
                to_remove = len(self.targets) - self.max_pool_size
                
                for i in range(to_remove):
                    symbol_to_remove = sorted_targets[i][0]
                    del self.targets[symbol_to_remove]
    
    def record_attempt_failure(self, symbol: str, reason: str):
        """
        Başarısız bir işlem girişimini kaydeder.
        
        Args:
            symbol (str): Başarısız olunan sembol
            reason (str): Başarısızlık nedeni
        """
        current_time = time.time()
        
        if symbol not in self.attempt_failures:
            self.attempt_failures[symbol] = {
                'count': 1,
                'last_failure': current_time,
                'reasons': [reason]
            }
        else:
            self.attempt_failures[symbol]['count'] += 1
            self.attempt_failures[symbol]['last_failure'] = current_time
            self.attempt_failures[symbol]['reasons'].append(reason)
            
        # Hedef havuzundaki skoru güncelle
        if symbol in self.targets:
            # Başarısızlık sayısına göre skoru düşür
            failure_count = self.attempt_failures[symbol]['count']
            penalty_factor = min(0.5, failure_count * 0.1)  # Maksimum %50 ceza
            
            self.targets[symbol]['score'] *= (1 - penalty_factor)
            logger.info(f"{symbol} için başarısız işlem girişimi kaydedildi. "
                       f"Skor düşürüldü: {penalty_factor*100:.1f}% ceza uygulandı")
    
    def record_success(self, symbol: str, data: Optional[Dict] = None):
        """
        Başarılı bir işlemi kaydeder.
        
        Args:
            symbol (str): Başarılı olunan sembol
            data (Dict, optional): Başarı verisi
        """
        current_time = time.time()
        
        if symbol not in self.success_history:
            self.success_history[symbol] = {
                'count': 1,
                'last_success': current_time,
                'data': data or {}
            }
        else:
            self.success_history[symbol]['count'] += 1
            self.success_history[symbol]['last_success'] = current_time
            if data:
                self.success_history[symbol]['data'] = data
        
        # Başarı nedeniyle skor artışı
        if symbol in self.targets:
            # Başarı sayısına göre skoru artır
            success_count = self.success_history[symbol]['count']
            bonus_factor = min(0.3, success_count * 0.05)  # Maksimum %30 bonus
            
            self.targets[symbol]['score'] *= (1 + bonus_factor)
            logger.info(f"{symbol} için başarılı işlem kaydedildi. "
                       f"Skor artırıldı: {bonus_factor*100:.1f}% bonus uygulandı")
    
    def is_symbol_cooling_down(self, symbol: str) -> bool:
        """
        Sembolün soğuma süresinde olup olmadığını kontrol eder.
        
        Başarısız işlem denemelerinden sonra sembol belirli bir süre soğumaya alınır.
        
        Args:
            symbol (str): Kontrol edilecek sembol
            
        Returns:
            bool: Sembol soğuma süresindeyse True, değilse False
        """
        if symbol not in self.attempt_failures:
            return False
            
        current_time = time.time()
        last_failure = self.attempt_failures[symbol]['last_failure']
        failure_count = self.attempt_failures[symbol]['count']
        
        # Başarısızlık sayısına göre soğuma süresi artar
        cooling_period = min(3600, failure_count * 300)  # 5 dakika * failure_count, maksimum 1 saat
        
        return (current_time - last_failure) < cooling_period
    
    async def get_top_targets(self, count: int = 10, exclude_cooling: bool = True) -> List[str]:
        """
        En yüksek puanlı hedefleri döndürür.
        
        Args:
            count (int): Döndürülecek hedef sayısı
            exclude_cooling (bool): Soğuma süresindeki sembolleri hariç tutma
            
        Returns:
            List[str]: Top hedef sembolleri
        """
        async with self.lock:
            targets_list = []
            
            # Soğuma sürecindeki sembolleri filtrele
            available_targets = {
                symbol: data for symbol, data in self.targets.items() 
                if not (exclude_cooling and self.is_symbol_cooling_down(symbol))
            }
            
            # Puana göre sırala
            sorted_targets = sorted(
                available_targets.items(), 
                key=lambda x: x[1].get('score', 0), 
                reverse=True
            )
            
            # En yüksek puanlı 'count' adet hedefi al
            top_targets = sorted_targets[:count]
            
            return [symbol for symbol, _ in top_targets]
            
    def get_target_data(self, symbol: str) -> Optional[Dict]:
        """
        Belirli bir sembol için hedef verilerini döndürür.
        
        Args:
            symbol (str): Veri alınacak sembol
            
        Returns:
            Optional[Dict]: Sembol verisi, sembol havuzda yoksa None
        """
        return self.targets.get(symbol)
        
    async def refresh_targets_data(self, symbols: List[str], market_data_manager, full_refresh: bool = False):
        """
        Hedef sembollerinin verilerini yeniler.
        
        Args:
            symbols (List[str]): Yenilenecek sembollerin listesi
            market_data_manager: MarketDataManager örneği
            full_refresh (bool): Tam yenileme yapılıp yapılmayacağı
        """
        current_time = time.time()
        
        # Tam yenileme için zamanlama kontrolü (10 dakikada bir)
        if full_refresh and (current_time - self.last_full_refresh) < 600:
            full_refresh = False
        
        # Tüm semboller için 24 saatlik ticker verilerini al - API'ye tek bir istek yapar
        all_tickers = await market_data_manager.client.get_ticker_24h()
        
        for symbol in symbols:
            try:
                # Son fiyat bilgisini al
                last_price = await market_data_manager.client.get_mark_price(symbol)
                
                # Fiyat yoksa atla
                if last_price <= 0:
                    continue
                
                # Sembol için ticker bilgisini bul
                ticker_24h = next((ticker for ticker in all_tickers if ticker['symbol'] == symbol), None)
                price_change_24h = float(ticker_24h.get('priceChangePercent', 0)) if ticker_24h else 0
                
                # Teknik göstergeleri hesapla (opsiyonel tam yenileme için)
                technical_data = {}
                
                if full_refresh:
                    # Temel zaman diliminde teknik göstergeleri hesapla
                    tf = market_data_manager.strategy.get('primary_timeframe')
                    df = await market_data_manager.calculate_technical_indicators(symbol, tf)
                    
                    if df is not None and len(df) > 0:
                        # Önemli göstergeleri çıkar
                        technical_data = {
                            'rsi': float(df['rsi'].iloc[-1]),
                            'macd': float(df['macd'].iloc[-1]),
                            'macd_signal': float(df['macd_signal'].iloc[-1]),
                            'bb_width': float(df['bb_width'].iloc[-1]),
                            'atr': float(df['atr'].iloc[-1]),
                            'adx': float(df['adx'].iloc[-1]),
                            'ema_trend': 1 if df['ema_short'].iloc[-1] > df['ema_medium'].iloc[-1] > df['ema_long'].iloc[-1] else
                                         -1 if df['ema_short'].iloc[-1] < df['ema_medium'].iloc[-1] < df['ema_long'].iloc[-1] else 0
                        }
                        
                        # RSI trend hesapla (son 5 mumdan)
                        if len(df) >= 5:
                            rsi_values = df['rsi'].iloc[-5:].values
                            rsi_trend = 1 if rsi_values[-1] > rsi_values[0] else -1 if rsi_values[-1] < rsi_values[0] else 0
                            technical_data['rsi_trend'] = rsi_trend
                
                # Hedef verisini güncelle
                target_data = {
                    'last_price': last_price,
                    'price_change_24h': price_change_24h,
                    'last_check': current_time
                }
                
                if technical_data:
                    target_data['technical'] = technical_data
                
                # Puanı hesapla
                opportunity_score = await market_data_manager.calculate_opportunity_score(
                    symbol, target_data, technical_data if full_refresh else {}
                )
                target_data['score'] = opportunity_score
                
                # UI'da kullanmak için opportunity_score'u da ekleyelim
                target_data['opportunity_score'] = opportunity_score
                
                # Hedefi güncelle
                await self.add_or_update_target(symbol, target_data)
                
            except Exception as e:
                logger.error(f"{symbol} hedef verisi güncellenirken hata: {e}")
        
        # Tam yenileme yapıldıysa son yenileme zamanını güncelle
        if full_refresh:
            self.last_full_refresh = current_time

class MarketDataManager:
    """Piyasa verilerini yönetir ve analiz eder."""
    
    def __init__(self, client: BinanceClient, strategy: StrategyParams):
        self.client = client
        self.strategy = strategy
        self.candle_data = {}  # {symbol: {timeframe: pd.DataFrame}}
        self.market_metrics = {}  # Piyasa metrikleri
        self.btc_metrics = {}  # BTC metrikleri (genel piyasa göstergesi olarak)
        self.last_update = {}  # Son güncelleme zamanları
        self.lock = asyncio.Lock()  # Veri güncellemesi için lock
        self.ui = None  # UI referansı
        
        # Dinamik hedef havuzu ekle
        self.target_pool = DynamicTargetPool(max_pool_size=100)
        
    async def initialize(self):
        """İlk verileri yükler."""
        logger.info("MarketDataManager başlatılıyor...")
        # BTC verilerini yükle (piyasa trend göstergesi olarak kullanılacak)
        await self.update_btc_metrics()
        logger.info("MarketDataManager başlatıldı.")
    
    async def update_candle_data(self, symbol: str, timeframe: str = '4h', limit: int = 100):
        """Belirli bir sembol ve zaman dilimi için mum verilerini günceller."""
        cache_key = f"{symbol}_{timeframe}"
        
        # Son güncelleme zamanını kontrol et
        current_time = time.time()
        if cache_key in self.last_update:
            elapsed = current_time - self.last_update[cache_key]
            
            # Zaman diliminine göre minimum güncelleme süresi
            min_update_interval = {
                '1m': 60, '3m': 180, '5m': 300, '15m': 900, '30m': 1800,
                '1h': 3600, '2h': 7200, '4h': 14400, '6h': 21600, '8h': 28800,
                '12h': 43200, '1d': 86400, '3d': 259200, '1w': 604800
            }.get(timeframe, 3600)
            
            # Yeterince zaman geçmediyse güncelleme yapma
            if elapsed < min_update_interval / 2:
                return self.candle_data.get(symbol, {}).get(timeframe)
        
        try:
            # Kline verilerini al
            klines = await self.client.get_historical_klines(
                symbol=symbol,
                interval=timeframe,
                limit=limit
            )
            
            # Pandas DataFrame'e dönüştür
            df = pd.DataFrame(klines, columns=[
                'open_time', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                'taker_buy_quote', 'ignore'
            ])
            
            # Veri tiplerini dönüştür
            numeric_columns = ['open', 'high', 'low', 'close', 'volume', 
                              'quote_volume', 'trades', 'taker_buy_base', 'taker_buy_quote']
            
            for col in numeric_columns:
                df[col] = pd.to_numeric(df[col])
            
            # Zaman sütunlarını datetime'a dönüştür
            df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
            df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')
            
            # Veriye ekstra bir kontrol uygula
            if len(df) < 20:  # Minimum analiz için gereken veri
                logger.warning(f"{symbol} {timeframe} için yeterli veri yok ({len(df)} satır)")
                return None
            
            # NaN değerleri doldur
            df.fillna(method='ffill', inplace=True)
            
            # Veriyi önbelleğe al
            if symbol not in self.candle_data:
                self.candle_data[symbol] = {}
            
            self.candle_data[symbol][timeframe] = df
            self.last_update[cache_key] = current_time
            
            return df
        except Exception as e:
            logger.error(f"{symbol} {timeframe} mum verileri güncellenirken hata: {e}")
            return None
    
    async def update_btc_metrics(self):
        """BTC metriklerini günceller (genel piyasa göstergesi olarak)."""
        try:
            # BTC verilerini farklı zaman dilimlerinde al
            timeframes = ['1h', '4h', '1d']
            btc_data = {}
            
            for tf in timeframes:
                df = await self.update_candle_data('BTCUSDT', tf, 100)
                if df is not None:
                    btc_data[tf] = df
            
            # Metrikleri hesapla
            self.btc_metrics = {
                'trend': await self._calculate_trend_metrics('BTCUSDT'),
                'volatility': await self._calculate_volatility_metrics('BTCUSDT'),
                'last_price': float(btc_data['1h']['close'].iloc[-1]) if '1h' in btc_data else 0,
                'daily_change': self._calculate_change_percent(btc_data['1d']) if '1d' in btc_data else 0,
                'hourly_change': self._calculate_change_percent(btc_data['1h']) if '1h' in btc_data else 0,
                'updated_at': datetime.now()
            }
            
            logger.info(f"BTC metrikleri güncellendi: Trend={self.btc_metrics['trend']:.2f}, "
                       f"Volatilite={self.btc_metrics['volatility']:.2f}, "
                       f"Günlük Değişim={self.btc_metrics['daily_change']:.2f}%")
        except Exception as e:
            logger.error(f"BTC metrikleri güncellenirken hata: {e}")
    
    async def update_market_metrics(self):
        """Genel piyasa metriklerini günceller."""
        try:
            # En yüksek hacimli sembolleri al
            top_volume = await self.client.get_top_volume_symbols(
                quote_asset=self.strategy.get('quote_asset'),
                limit=20
            )
            
            # Ortalama hacim ve volatilite bilgilerini hesapla
            total_volume = sum(float(ticker['quoteVolume']) for ticker in top_volume)
            avg_volume = total_volume / len(top_volume) if top_volume else 0
            
            # Volatilite hesapla (24 saatlik fiyat değişimi yüzdesi)
            volatilities = [abs(float(ticker['priceChangePercent'])) for ticker in top_volume]
            avg_volatility = sum(volatilities) / len(volatilities) if volatilities else 0
            
            # Yükselenler vs düşenler
            gainers = sum(1 for ticker in top_volume if float(ticker['priceChangePercent']) > 0)
            losers = sum(1 for ticker in top_volume if float(ticker['priceChangePercent']) < 0)
            
            # Trend skorunu hesapla (-100 ile 100 arasında)
            # Pozitif değerler yükselen piyasayı, negatif değerler düşen piyasayı gösterir
            if gainers + losers > 0:
                trend_score = 100 * (gainers - losers) / (gainers + losers)
            else:
                trend_score = 0
            
            # Piyasa metriklerini güncelle
            self.market_metrics = {
                'avg_volume': avg_volume,
                'avg_volatility': avg_volatility,
                'trend_score': trend_score,
                'gainers_count': gainers,
                'losers_count': losers,
                'total_symbols': len(top_volume),
                'btc_dominance': self.btc_metrics.get('trend', 0),
                'updated_at': datetime.now()
            }
            
            logger.info(f"Piyasa metrikleri güncellendi: Trend={trend_score:.2f}, "
                       f"Volatilite={avg_volatility:.2f}%, "
                       f"Yükselenler/Düşenler={gainers}/{losers}")
        except Exception as e:
            logger.error(f"Piyasa metrikleri güncellenirken hata: {e}")
    
    async def get_market_state(self):
        """Piyasa durumunu döndürür."""
        # BTC ve piyasa metriklerini kontrol et
        btc_metrics = self.btc_metrics
        market_metrics = self.market_metrics
        
        if not btc_metrics or not market_metrics:
            await self.update_btc_metrics()
            await self.update_market_metrics()
            btc_metrics = self.btc_metrics
            market_metrics = self.market_metrics
        
        # Piyasa durumunu belirle
        btc_trend = btc_metrics.get('trend', 0)
        market_trend = market_metrics.get('trend_score', 0)
        
        # Ağırlıklı trend skoru (BTC %60, genel piyasa %40)
        weighted_trend = btc_trend * 0.6 + market_trend * 0.4
        
        # Piyasa durumunu sınıflandır
        if weighted_trend > 50:
            market_state = "BULLISH"
        elif weighted_trend > 20:
            market_state = "SLIGHTLY_BULLISH"
        elif weighted_trend > -20:
            market_state = "NEUTRAL"
        elif weighted_trend > -50:
            market_state = "SLIGHTLY_BEARISH"
        else:
            market_state = "BEARISH"
        
        # Volatilite durumunu belirle
        btc_volatility = btc_metrics.get('volatility', 0)
        market_volatility = market_metrics.get('avg_volatility', 0)
        
        # Ağırlıklı volatilite (BTC %50, genel piyasa %50)
        weighted_volatility = btc_volatility * 0.5 + market_volatility * 0.5
        
        # Volatilite durumunu sınıflandır
        if weighted_volatility > 5:
            volatility_state = "EXTREME"
        elif weighted_volatility > 3:
            volatility_state = "HIGH"
        elif weighted_volatility > 1.5:
            volatility_state = "MODERATE"
        else:
            volatility_state = "LOW"
        
        return {
            "market_state": market_state,
            "volatility_state": volatility_state,
            "trend_score": weighted_trend,
            "volatility_score": weighted_volatility,
            "btc_trend": btc_trend,
            "btc_volatility": btc_volatility,
            "market_trend": market_trend,
            "market_volatility": market_volatility,
            "updated_at": datetime.now()
        }
    
    async def _calculate_trend_metrics(self, symbol: str) -> float:
        """Sembol için trend metriklerini hesaplar."""
        try:
            # Farklı zaman dilimlerindeki trend göstergelerini hesapla
            timeframes = ['1h', '4h', '1d']
            trend_scores = []
            
            for tf in timeframes:
                if symbol not in self.candle_data or tf not in self.candle_data[symbol]:
                    await self.update_candle_data(symbol, tf)
                
                if symbol in self.candle_data and tf in self.candle_data[symbol]:
                    df = self.candle_data[symbol][tf]
                    
                    # EMA hesaplamaları
                    ema_short = EMAIndicator(close=df['close'], window=self.strategy.get('ema_short')).ema_indicator()
                    ema_medium = EMAIndicator(close=df['close'], window=self.strategy.get('ema_medium')).ema_indicator()
                    ema_long = EMAIndicator(close=df['close'], window=self.strategy.get('ema_long')).ema_indicator()
                    
                    # MACD hesaplaması
                    macd = MACD(
                        close=df['close'],
                        window_slow=self.strategy.get('macd_slow'),
                        window_fast=self.strategy.get('macd_fast'),
                        window_sign=self.strategy.get('macd_signal')
                    )
                    
                    # Son değerleri al
                    last_close = df['close'].iloc[-1]
                    last_ema_short = ema_short.iloc[-1]
                    last_ema_medium = ema_medium.iloc[-1]
                    last_ema_long = ema_long.iloc[-1]
                    last_macd = macd.macd().iloc[-1]
                    last_macd_signal = macd.macd_signal().iloc[-1]
                    
                    # Trend skorunu hesapla (100 ile -100 arasında)
                    score = 0
                    
                    # EMA düzenine göre trend belirle (golden cross / death cross)
                    if last_ema_short > last_ema_medium > last_ema_long:
                        score += 40  # Güçlü yükselen trend
                    elif last_ema_short > last_ema_medium:
                        score += 20  # Orta yükselen trend
                    elif last_ema_short < last_ema_medium < last_ema_long:
                        score -= 40  # Güçlü düşen trend
                    elif last_ema_short < last_ema_medium:
                        score -= 20  # Orta düşen trend
                    
                    # Fiyatın EMA'lara göre konumu
                    if last_close > last_ema_short:
                        score += 10
                    if last_close > last_ema_medium:
                        score += 15
                    if last_close > last_ema_long:
                        score += 20
                    if last_close < last_ema_short:
                        score -= 10
                    if last_close < last_ema_medium:
                        score -= 15
                    if last_close < last_ema_long:
                        score -= 20
                    
                    # MACD sinyali
                    if last_macd > last_macd_signal:
                        score += 15
                    else:
                        score -= 15
                    
                    # MACD'nin sıfır çizgisine göre durumu
                    if last_macd > 0:
                        score += 10
                    else:
                        score -= 10
                    
                    # Skoru sınırla (-100 ile 100 arası)
                    score = max(-100, min(100, score))
                    
                    # Zaman dilimine göre ağırlık belirle
                    if tf == '1h':
                        weight = 0.2
                    elif tf == '4h':
                        weight = 0.3
                    else:  # 1d
                        weight = 0.5
                    
                    trend_scores.append((score, weight))
            
            # Ağırlıklı trend skorunu hesapla
            if trend_scores:
                weighted_score = sum(score * weight for score, weight in trend_scores)
                total_weight = sum(weight for _, weight in trend_scores)
                if total_weight > 0:
                    return weighted_score / total_weight
            
            return 0  # Veri yoksa nötr dön
        except Exception as e:
            logger.error(f"Trend metrikleri hesaplanırken hata: {e}")
            return 0
    
    async def _calculate_volatility_metrics(self, symbol: str) -> float:
        """Sembol için volatilite metriklerini hesaplar."""
        try:
            # 1h ve 4h zaman dilimlerinde ATR hesapla
            timeframes = ['1h', '4h']
            volatility_values = []
            
            for tf in timeframes:
                if symbol not in self.candle_data or tf not in self.candle_data[symbol]:
                    await self.update_candle_data(symbol, tf)
                
                if symbol in self.candle_data and tf in self.candle_data[symbol]:
                    df = self.candle_data[symbol][tf]
                    
                    # ATR hesapla
                    atr = AverageTrueRange(
                        high=df['high'],
                        low=df['low'],
                        close=df['close'],
                        window=self.strategy.get('atr_length')
                    ).average_true_range()
                    
                    if len(atr) > 0:
                        last_atr = atr.iloc[-1]
                        last_close = df['close'].iloc[-1]
                        
                        # ATR'yi fiyata göre normalize et (% olarak)
                        normalized_atr = (last_atr / last_close) * 100
                        
                        # Zaman dilimine göre ağırlık belirle
                        if tf == '1h':
                            weight = 0.4
                        else:  # 4h
                            weight = 0.6
                        
                        volatility_values.append((normalized_atr, weight))
            
            # Ağırlıklı volatilite değerini hesapla
            if volatility_values:
                weighted_volatility = sum(vol * weight for vol, weight in volatility_values)
                total_weight = sum(weight for _, weight in volatility_values)
                if total_weight > 0:
                    return weighted_volatility / total_weight
            
            return 1.0  # Veri yoksa orta volatilite dön
        except Exception as e:
            logger.error(f"Volatilite metrikleri hesaplanırken hata: {e}")
            return 1.0
    
    def _calculate_change_percent(self, df: pd.DataFrame) -> float:
        """Dataframe'deki son fiyat değişim yüzdesini hesaplar."""
        if df is None or len(df) < 2:
            return 0
        
        last_close = df['close'].iloc[-1]
        prev_close = df['close'].iloc[-2]
        
        if prev_close == 0:
            return 0
        
        return ((last_close - prev_close) / prev_close) * 100
    
    async def get_filtered_symbols(self, min_volume=None):
        """Filtrelenmiş sembol listesini döndürür."""
        try:
            # Minimum hacim değerini kontrol et
            if min_volume is None:
                min_volume = self.strategy.get('min_volume_usdt')
            
            # 24 saatlik ticker bilgisini al
            all_tickers = await self.client.get_ticker_24h()
            
            # Quote asset filtresi
            filtered_tickers = [
                ticker for ticker in all_tickers
                if ticker['symbol'].endswith(self.strategy.get('quote_asset'))
            ]
            
            # Hacim filtresi
            filtered_tickers = [
                ticker for ticker in filtered_tickers
                if float(ticker['quoteVolume']) >= min_volume
            ]
            
            # Sembolleri al
            symbols = [ticker['symbol'] for ticker in filtered_tickers]
            
            # Strateji parametrelerindeki whitelist/blacklist filtresini uygula
            symbols = self.strategy.get_trading_symbols(symbols)
            
            return symbols
        except Exception as e:
            logger.error(f"Semboller filtrelenirken hata: {e}")
            return []
    
    async def calculate_technical_indicators(self, symbol: str, timeframe: str):
        """Teknik göstergeleri hesaplar ve dataframe'e ekler."""
        try:
            if symbol not in self.candle_data or timeframe not in self.candle_data[symbol]:
                await self.update_candle_data(symbol, timeframe)
            
            if symbol not in self.candle_data or timeframe not in self.candle_data[symbol]:
                logger.error(f"{symbol} {timeframe} için mum verileri alınamadı")
                return None
            
            df = self.candle_data[symbol][timeframe].copy()
            
            # RSI
            df['rsi'] = RSIIndicator(
                close=df['close'],
                window=self.strategy.get('rsi_length')
            ).rsi()
            
            # MACD
            macd = MACD(
                close=df['close'],
                window_slow=self.strategy.get('macd_slow'),
                window_fast=self.strategy.get('macd_fast'),
                window_sign=self.strategy.get('macd_signal')
            )
            df['macd'] = macd.macd()
            df['macd_signal'] = macd.macd_signal()
            df['macd_histogram'] = macd.macd_diff()
            
            # Bollinger Bands
            bb = BollingerBands(
                close=df['close'],
                window=self.strategy.get('bb_length'),
                window_dev=self.strategy.get('bb_std_dev')
            )
            df['bb_upper'] = bb.bollinger_hband()
            df['bb_middle'] = bb.bollinger_mavg()
            df['bb_lower'] = bb.bollinger_lband()
            df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
            
            # ATR
            df['atr'] = AverageTrueRange(
                high=df['high'],
                low=df['low'],
                close=df['close'],
                window=self.strategy.get('atr_length')
            ).average_true_range()
            
            # EMA'lar
            df['ema_short'] = EMAIndicator(
                close=df['close'],
                window=self.strategy.get('ema_short')
            ).ema_indicator()
            
            df['ema_medium'] = EMAIndicator(
                close=df['close'],
                window=self.strategy.get('ema_medium')
            ).ema_indicator()
            
            df['ema_long'] = EMAIndicator(
                close=df['close'],
                window=self.strategy.get('ema_long')
            ).ema_indicator()
            
            # Stochastic Oscillator
            stoch = StochasticOscillator(
                high=df['high'],
                low=df['low'],
                close=df['close'],
                window=self.strategy.get('stoch_k'),
                smooth_window=self.strategy.get('stoch_d')
            )
            df['stoch_k'] = stoch.stoch()
            df['stoch_d'] = stoch.stoch_signal()
            
            # ADX
            adx = ADXIndicator(
                high=df['high'],
                low=df['low'],
                close=df['close'],
                window=self.strategy.get('adx_length')
            )
            df['adx'] = adx.adx()
            df['di_plus'] = adx.adx_pos()
            df['di_minus'] = adx.adx_neg()
            
            # Hacim indikatörleri
            df['obv'] = OnBalanceVolumeIndicator(
                close=df['close'],
                volume=df['volume']
            ).on_balance_volume()
            
            df['vpt'] = VolumePriceTrendIndicator(
                close=df['close'],
                volume=df['volume']
            ).volume_price_trend()
            
            # Ichimoku
            ichimoku = IchimokuIndicator(
                high=df['high'],
                low=df['low'],
                window1=self.strategy.get('ichimoku_fast'),
                window2=self.strategy.get('ichimoku_med'),
                window3=self.strategy.get('ichimoku_slow')
            )
            df['ichimoku_conversion'] = ichimoku.ichimoku_conversion_line()
            df['ichimoku_base'] = ichimoku.ichimoku_base_line()
            df['ichimoku_a'] = ichimoku.ichimoku_a()
            df['ichimoku_b'] = ichimoku.ichimoku_b()
            
            # NaN değerleri doldur
            df.fillna(method='ffill', inplace=True)
            df.fillna(method='bfill', inplace=True)
            df.fillna(0, inplace=True)
            
            # Güncellenmiş dataframe'i kaydet
            self.candle_data[symbol][timeframe] = df
            
            return df
        except Exception as e:
            logger.error(f"{symbol} {timeframe} için teknik göstergeler hesaplanırken hata: {e}")
            return None
    
    # YENİ METODLAR
    
    async def get_top_opportunity_symbols(self, count: int = 10, exclude_cooling: bool = True) -> List[str]:
        """
        En yüksek fırsat puanına sahip sembolleri döndürür.
        
        Args:
            count (int): Alınacak sembol sayısı
            exclude_cooling (bool): Soğuma sürecindeki sembolleri hariç tut
            
        Returns:
            List[str]: En yüksek fırsat puanlı semboller listesi
        """
        # Hedef havuzundan en yüksek puanlı sembolleri al
        return await self.target_pool.get_top_targets(count, exclude_cooling)
    
    async def refresh_symbol_opportunities(self, symbols: List[str], full_refresh: bool = False):
        """
        Belirtilen sembollerin fırsat puanlarını ve hedef havuzunu günceller.
        
        Args:
            symbols (List[str]): Güncellenecek semboller listesi
            full_refresh (bool): Tam yenileme yapılıp yapılmayacağı
        """
        await self.target_pool.refresh_targets_data(symbols, self, full_refresh)
    
    async def calculate_opportunity_score(self, symbol: str, price_data: Dict, technical_data: Dict = None) -> float:
        """
        Sembol için fırsat puanını hesaplar.
        
        Args:
            symbol (str): İncelenecek sembol
            price_data (Dict): Fiyat verileri içeren sözlük
            technical_data (Dict, optional): Teknik gösterge verileri
            
        Returns:
            float: 0-100 arasında fırsat puanı
        """
        try:
            # Temel puan - her sembol için başlangıç puanı
            base_score = 50.0
            
            # Fiyat değişim puanı - 24 saatlik değişim
            price_change = price_data.get('price_change_24h', 0)
            price_change_score = 0
            
            # Fiyat değişimi için puan hesaplama: yüksek hareket = yüksek fırsat
            if abs(price_change) > 10:  # %10'dan fazla hareket
                price_change_score = 20  # Yüksek puan
            elif abs(price_change) > 5:  # %5'den fazla hareket
                price_change_score = 15
            elif abs(price_change) > 2:  # %2'den fazla hareket
                price_change_score = 10
            else:
                price_change_score = 5   # Düşük hareket = düşük puan
            
            # Volatilite avantajı: market_state yüksek volatilite gösteriyorsa bonus
            market_state = await self.get_market_state()
            volatility_score = market_state.get('volatility_score', 1.0)
            
            volatility_bonus = 0
            if volatility_score > 3:  # Yüksek volatilite
                volatility_bonus = 10
            elif volatility_score > 2:  # Orta volatilite
                volatility_bonus = 5
            
            # Teknik gösterge puanları (teknik veriler varsa)
            technical_score = 0
            
            if technical_data:
                # RSI değerlendirmesi
                rsi = technical_data.get('rsi', 50)
                rsi_score = 0
                
                if rsi < 30:  # Aşırı satım
                    rsi_score = 15
                elif rsi > 70:  # Aşırı alım
                    rsi_score = 10
                else:
                    rsi_score = 5
                
                # RSI trend bonus
                rsi_trend = technical_data.get('rsi_trend', 0)
                if rsi_trend != 0:
                    rsi_score += 5
                
                # MACD değerlendirmesi
                macd = technical_data.get('macd', 0)
                macd_signal = technical_data.get('macd_signal', 0)
                macd_score = 0
                
                # MACD kesişim kontrolü
                if (macd > 0 and macd_signal > 0) or (macd < 0 and macd_signal < 0):
                    # Aynı tarafta
                    macd_score = 5
                
                # Kesişme yakın mı?
                if abs(macd - macd_signal) < 0.0005:
                    macd_score += 10  # Kesişmeye yakın = yüksek fırsat
                
                # EMA trend değerlendirmesi
                ema_trend = technical_data.get('ema_trend', 0)
                ema_score = 0
                
                if ema_trend != 0:  # Belirgin trend varsa
                    ema_score = 10
                    
                # ADX değerlendirmesi - güçlü trend
                adx = technical_data.get('adx', 0)
                adx_score = 0
                
                if adx > 30:  # Güçlü trend
                    adx_score = 15
                elif adx > 20:  # Orta trend
                    adx_score = 10
                else:
                    adx_score = 5
                
                # Bollinger Band genişliği - volatilite göstergesi
                bb_width = technical_data.get('bb_width', 1.0)
                bb_score = 0
                
                if bb_width < 0.1:  # Çok dar BB = genişleme beklentisi
                    bb_score = 15
                elif bb_width < 0.2:  # Dar BB
                    bb_score = 10
                    
                # Tüm teknik puanları topla ve normalize et
                technical_score = (rsi_score + macd_score + ema_score + adx_score + bb_score) / 5
            
            # Toplam puanı hesapla (eşit ağırlıklarla)
            final_score = base_score + price_change_score + volatility_bonus
            
            if technical_score > 0:
                final_score = (final_score + technical_score) / 2
            
            # Soğuma faktörü - başarısız işlem girişimleri için ceza
            cooling_factor = 1.0
            
            if symbol in self.target_pool.attempt_failures:
                failures = self.target_pool.attempt_failures[symbol]
                failure_count = failures.get('count', 0)
                last_failure = failures.get('last_failure', 0)
                current_time = time.time()
                time_since_failure = current_time - last_failure
                
                # Başarısızlık sayısına ve geçen zamana göre ceza
                if time_since_failure < 3600:  # Son bir saat içinde
                    cooling_factor = max(0.3, 1 - (failure_count * 0.1))  # Her başarısızlık için %10 ceza, minimum %30
                elif time_since_failure < 7200:  # 1-2 saat arası
                    cooling_factor = max(0.6, 1 - (failure_count * 0.05))  # Her başarısızlık için %5 ceza, minimum %60
                
            # Başarı geçmişi bonusu
            success_factor = 1.0
            
            if symbol in self.target_pool.success_history:
                success = self.target_pool.success_history[symbol]
                success_count = success.get('count', 0)
                
                # Başarı sayısına göre bonus
                success_factor = min(1.5, 1 + (success_count * 0.05))  # Her başarı için %5 bonus, maksimum %50
            
            # Son faktörleri uygula
            final_score = final_score * cooling_factor * success_factor
            
            # Puanı 0-100 aralığına sınırla
            final_score = max(0, min(100, final_score))
            
            return final_score
            
        except Exception as e:
            logger.error(f"{symbol} için fırsat puanı hesaplanırken hata: {e}")
            return 0
    
    def record_trade_attempt_failure(self, symbol: str, reason: str):
        """
        Başarısız bir işlem girişimini kaydeder.
        
        Args:
            symbol (str): Başarısız işlemin sembolü
            reason (str): Başarısızlık nedeni
        """
        self.target_pool.record_attempt_failure(symbol, reason)
    
    def record_trade_success(self, symbol: str, data: Optional[Dict] = None):
        """
        Başarılı bir işlemi kaydeder.
        
        Args:
            symbol (str): Başarılı işlemin sembolü
            data (Dict, optional): İşlem verisi
        """
        self.target_pool.record_success(symbol, data)