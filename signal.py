"""
Teknik analiz sinyallerini üreten sınıf
"""

import asyncio
import logging
import traceback
from typing import Dict, List, Optional, Tuple
from datetime import datetime

import pandas as pd

from trading_bot.core.market_data import MarketDataManager
from trading_bot.core.strategy import StrategyParams

logger = logging.getLogger("trading_bot")

class SignalGenerator:
    """Teknik analiz sinyallerini üreten sınıf."""
    
    def __init__(self, market_data: MarketDataManager, strategy: StrategyParams):
        self.market_data = market_data
        self.strategy = strategy
        self.signal_cache = {}  # Son sinyalleri önbellekte tut
        self.signal_lock = asyncio.Lock()  # Sinyal üretimi için lock
        self.ui = None  # UI referansı için alan
    
    async def generate_signal(self, symbol: str) -> Dict:
        """Sembol için ticaret sinyali üretir."""
        async with self.signal_lock:
            try:
                # Mevcut piyasa durumunu al
                market_state = await self.market_data.get_market_state()
                
                # Primary ve secondary zaman dilimlerini al
                primary_tf = self.strategy.get('primary_timeframe')
                secondary_tfs = self.strategy.get('secondary_timeframes')
                
                # Tüm zaman dilimlerini tek bir listede topla
                timeframes = [primary_tf] + secondary_tfs
                
                # Her zaman dilimi için teknik göstergeleri hesapla
                df_dict = {}
                for tf in timeframes:
                    df = await self.market_data.calculate_technical_indicators(symbol, tf)
                    if df is not None:
                        df_dict[tf] = df
                
                if not df_dict:
                    logger.warning(f"{symbol} için herhangi bir zaman diliminde veri alınamadı")
                    return self._create_neutral_signal(symbol, "Veri alınamadı")
                
                # Zaman dilimine göre ağırlıklar
                tf_weights = self._get_timeframe_weights(timeframes)
                
                # Her zaman dilimi için sinyaller hesapla
                signals_by_tf = {}
                for tf, df in df_dict.items():
                    signals_by_tf[tf] = self._calculate_signals_for_timeframe(df, tf, market_state)
                
                # Ağırlıklı sinyalleri birleştir
                long_score = 0
                short_score = 0
                total_weight = 0
                
                for tf, signals in signals_by_tf.items():
                    weight = tf_weights.get(tf, 1.0)
                    long_score += signals['long_score'] * weight
                    short_score += signals['short_score'] * weight
                    total_weight += weight
                
                if total_weight > 0:
                    long_score /= total_weight
                    short_score /= total_weight
                
                # Konsolidasyon kontrolü
                consolidation = self._detect_consolidation(df_dict[primary_tf])
                
                # Divergence kontrolü
                divergence = self._detect_divergence(df_dict[primary_tf])
                
                # Son fiyat bilgisi
                last_price = float(df_dict[primary_tf]['close'].iloc[-1])
                
                # Funding rate kontrolü
                funding_rate = await self._check_funding_rate(symbol)
                
                # Sinyal son değerlerini hesapla
                signal_strength = max(long_score, short_score)
                signal_type = "LONG" if long_score > short_score else "SHORT"
                
                # Son mumların verisini al
                recent_candles = self._extract_recent_candles(df_dict[primary_tf])
                
                # Giriş/çıkış zamanlaması değerlendirmesi
                timing_data = {
                    "rsi": float(df_dict[primary_tf]['rsi'].iloc[-1]),
                    "recent_candles": recent_candles,
                    "macd": float(df_dict[primary_tf]['macd'].iloc[-1]),
                    "macd_signal": float(df_dict[primary_tf]['macd_signal'].iloc[-1]),
                    "bb_width": float(df_dict[primary_tf]['bb_width'].iloc[-1]),
                    "atr": float(df_dict[primary_tf]['atr'].iloc[-1]),
                    "adx": float(df_dict[primary_tf]['adx'].iloc[-1])
                }
                
                timing_score = self.evaluate_entry_timing(symbol, signal_type, timing_data)
                
                # İşlem yapılabilir mi kontrol et
                tradable = self._is_signal_tradable(
                    signal_type, 
                    signal_strength,
                    timing_score,
                    market_state,
                    funding_rate
                )
                
                # Detaylı sinyal bilgilerini oluştur
                signal = {
                    'symbol': symbol,
                    'timestamp': datetime.now(),
                    'last_price': last_price,
                    'signal': signal_type if tradable else "NEUTRAL",
                    'long_score': round(long_score, 2),
                    'short_score': round(short_score, 2),
                    'signal_strength': round(signal_strength, 2),
                    'timing_score': round(timing_score, 2),
                    'tradable': tradable,
                    'market_state': market_state['market_state'],
                    'volatility_state': market_state['volatility_state'],
                    'consolidation': consolidation,
                    'divergence': divergence,
                    'funding_rate': funding_rate,
                    'indicators': {
                        tf: self._extract_key_indicators(df) for tf, df in df_dict.items()
                    },
                    'reasons': {
                        tf: signals['reasons'] for tf, signals in signals_by_tf.items()
                    }
                }
                
                # Sinyali önbelleğe al
                self.signal_cache[symbol] = {
                    'signal': signal,
                    'timestamp': datetime.now()
                }
                
                return signal
            except Exception as e:
                logger.error(f"{symbol} için sinyal üretilirken hata: {e}\n{traceback.format_exc()}")
                return self._create_neutral_signal(symbol, f"Hata: {str(e)}")
    
    def evaluate_entry_timing(self, symbol: str, signal_type: str, technical_data: Dict) -> float:
        """Giriş zamanlamasını değerlendirir ve optimallik puanı döndürür"""
        try:
            timing_score = 100  # Başlangıç skoru
            
            # RSI değerlendirmesi
            rsi = technical_data.get('rsi', 50)
            if signal_type == "LONG" and rsi > 70:
                timing_score -= (rsi - 70) * 2  # RSI yüksekse LONG için skor düşür
            elif signal_type == "SHORT" and rsi < 30:
                timing_score -= (30 - rsi) * 2  # RSI düşükse SHORT için skor düşür
            
            # Son mumların hareketini değerlendir
            recent_candles = technical_data.get('recent_candles', [])
            if len(recent_candles) >= 3:
                # Son 3 mumun yönü sinyalle aynı mı kontrol et
                consecutive_same_direction = 0
                for candle in recent_candles[-3:]:
                    if (signal_type == "LONG" and candle['close'] > candle['open']) or \
                       (signal_type == "SHORT" and candle['close'] < candle['open']):
                        consecutive_same_direction += 1
                
                # 3 ardışık aynı yönlü mum varsa, bu aşırı alım/satım olabilir
                if consecutive_same_direction == 3:
                    timing_score -= 15
                    logger.debug(f"{symbol}: 3 ardışık aynı yönlü mum tespit edildi, zamanlama skoru düşürüldü")
            
            # MACD giriş zamanlaması
            macd = technical_data.get('macd', 0)
            macd_signal = technical_data.get('macd_signal', 0)
            
            # MACD kesişme noktasından ne kadar uzaktayız?
            macd_diff = abs(macd - macd_signal)
            macd_ideal = False
            
            if signal_type == "LONG" and macd > macd_signal:
                # LONG sinyali için ideal MACD durumu: yeni kesişim oluşmuş
                if macd_diff < 0.0002:  # Çok yakın kesişim
                    timing_score += 15
                    macd_ideal = True
            elif signal_type == "SHORT" and macd < macd_signal:
                # SHORT sinyali için ideal MACD durumu: yeni kesişim oluşmuş
                if macd_diff < 0.0002:  # Çok yakın kesişim
                    timing_score += 15
                    macd_ideal = True
            
            # Bollinger Bandı durumu
            bb_width = technical_data.get('bb_width', 1.0)
            if bb_width < 0.1:  # Çok dar BB - genişleme beklenir
                timing_score += 10
                logger.debug(f"{symbol}: Dar Bollinger Bandı, genişleme bekleniyor, zamanlama skoru artırıldı")
            elif bb_width > 0.3:  # Çok geniş BB - daralma beklenir
                timing_score -= 10
                logger.debug(f"{symbol}: Geniş Bollinger Bandı, daralma bekleniyor, zamanlama skoru düşürüldü")
            
            # ATR değerlendirmesi - yüksek volatilite zamanlama için iyi değildir
            atr = technical_data.get('atr', 0)
            if atr > technical_data.get('atr_avg', atr) * 1.5:  # Ortalamanın 1.5 katı ATR
                timing_score -= 15
                logger.debug(f"{symbol}: Yüksek ATR (volatilite), zamanlama skoru düşürüldü")
            
            # ADX değerlendirmesi - güçlü trend zamanlaması
            adx = technical_data.get('adx', 0)
            if adx > 25 and not macd_ideal:  # Güçlü trend varsa ama MACD ideal değilse
                timing_score -= 10  # Trendin başlangıcını kaçırmış olabiliriz
            elif adx > 40:  # Çok güçlü trend
                timing_score -= 15  # Trend çok olgunlaşmış olabilir
            
            # Skorun makul sınırlar içinde olmasını sağla
            timing_score = max(0, min(100, timing_score))
            
            return timing_score
        except Exception as e:
            logger.error(f"{symbol} için giriş zamanlaması değerlendirilirken hata: {e}")
            return 50  # Hata durumunda nötr bir skor döndür
    
    def _extract_recent_candles(self, df: pd.DataFrame) -> List[Dict]:
        """Son 5 mumun özelliklerini çıkarır"""
        try:
            if df is None or len(df) < 5:
                return []
            
            recent_candles = []
            
            for i in range(-5, 0):
                candle = {
                    'open': float(df['open'].iloc[i]),
                    'high': float(df['high'].iloc[i]),
                    'low': float(df['low'].iloc[i]),
                    'close': float(df['close'].iloc[i]),
                    'volume': float(df['volume'].iloc[i]),
                    'body_size': abs(float(df['close'].iloc[i]) - float(df['open'].iloc[i])),
                    'is_bullish': float(df['close'].iloc[i]) > float(df['open'].iloc[i])
                }
                recent_candles.append(candle)
            
            return recent_candles
        except Exception as e:
            logger.error(f"Son mumlar çıkarılırken hata: {e}")
            return []
    
    def _create_neutral_signal(self, symbol: str, reason: str = "") -> Dict:
        """Nötr bir sinyal oluşturur."""
        return {
            'symbol': symbol,
            'timestamp': datetime.now(),
            'last_price': 0,
            'signal': "NEUTRAL",
            'long_score': 0,
            'short_score': 0,
            'signal_strength': 0,
            'timing_score': 0,
            'tradable': False,
            'market_state': "UNKNOWN",
            'volatility_state': "UNKNOWN",
            'consolidation': False,
            'divergence': None,
            'funding_rate': 0,
            'indicators': {},
            'reasons': {"primary": [reason] if reason else []}
        }
    
    def _get_timeframe_weights(self, timeframes: List[str]) -> Dict[str, float]:
        """Zaman dilimlerine göre ağırlıkları belirler."""
        # Varsayılan ağırlıklar
        weights = {
            '1m': 0.1, '3m': 0.15, '5m': 0.2, '15m': 0.3, '30m': 0.4,
            '1h': 0.6, '2h': 0.7, '4h': 0.8, '6h': 0.85, '8h': 0.9,
            '12h': 0.95, '1d': 1.0, '3d': 1.1, '1w': 1.2
        }
        
        # Primary timeframe olarak belirtilen zaman diliminin ağırlığını artır
        primary_tf = self.strategy.get('primary_timeframe')
        if primary_tf in weights:
            weights[primary_tf] *= 1.5
        
        # Parametre olarak belirtilen zaman dilimlerinin ağırlıklarını döndür
        return {tf: weights.get(tf, 0.5) for tf in timeframes}
    
    def _calculate_signals_for_timeframe(self, df: pd.DataFrame, timeframe: str, market_state: Dict) -> Dict:
        """Belirli bir zaman dilimi için sinyal hesaplar."""
        try:
            if df is None or len(df) < 20:  # En az 20 mum gerekli
                return {'long_score': 0, 'short_score': 0, 'reasons': []}
            
            # Son değerleri al
            last_idx = len(df) - 1
            
            # Boş sinyal başlat
            long_score = 0
            short_score = 0
            reasons = []
            
            # RSI sinyalleri
            rsi = df['rsi'].iloc[last_idx]
            rsi_prev = df['rsi'].iloc[last_idx - 1]
            
            # RSI aşırı alım/satım durumları
            if rsi < self.strategy.get('rsi_oversold'):
                long_score += 20 * self.strategy.get('rsi_weight')
                reasons.append(f"RSI aşırı satım bölgesinde: {rsi:.2f}")
            elif rsi > self.strategy.get('rsi_overbought'):
                short_score += 20 * self.strategy.get('rsi_weight')
                reasons.append(f"RSI aşırı alım bölgesinde: {rsi:.2f}")
            
            # RSI trend değişimi sinyalleri
            if rsi_prev < 30 and rsi > 30:
                long_score += 15 * self.strategy.get('rsi_weight')
                reasons.append(f"RSI 30 seviyesini yukarı kırdı: {rsi:.2f}")
            elif rsi_prev > 70 and rsi < 70:
                short_score += 15 * self.strategy.get('rsi_weight')
                reasons.append(f"RSI 70 seviyesini aşağı kırdı: {rsi:.2f}")
            
            # MACD sinyalleri
            macd = df['macd'].iloc[last_idx]
            macd_signal = df['macd_signal'].iloc[last_idx]
            macd_prev = df['macd'].iloc[last_idx - 1]
            macd_signal_prev = df['macd_signal'].iloc[last_idx - 1]
            
            # MACD kesişme sinyalleri
            if macd_prev < macd_signal_prev and macd > macd_signal:
                long_score += 25 * self.strategy.get('macd_weight')
                reasons.append("MACD sinyal çizgisini yukarı kesti")
            elif macd_prev > macd_signal_prev and macd < macd_signal:
                short_score += 25 * self.strategy.get('macd_weight')
                reasons.append("MACD sinyal çizgisini aşağı kesti")
            
            # MACD sıfır çizgisi geçişleri
            if macd_prev < 0 and macd > 0:
                long_score += 10 * self.strategy.get('macd_weight')
                reasons.append("MACD sıfır çizgisini yukarı kesti")
            elif macd_prev > 0 and macd < 0:
                short_score += 10 * self.strategy.get('macd_weight')
                reasons.append("MACD sıfır çizgisini aşağı kesti")
            
            # Bollinger Bands sinyalleri
            bb_upper = df['bb_upper'].iloc[last_idx]
            bb_lower = df['bb_lower'].iloc[last_idx]
            bb_width = df['bb_width'].iloc[last_idx]
            bb_width_prev = df['bb_width'].iloc[last_idx - 5]  # 5 mum önceki genişlik
            close = df['close'].iloc[last_idx]
            close_prev = df['close'].iloc[last_idx - 1]
            
            # BB sıkışma ve genişleme sinyalleri
            if bb_width < 0.1:  # Çok dar BB
                reasons.append(f"Bollinger Bandı daralması: {bb_width:.4f}")
                
                # BB daraldıktan sonra fiyat alt banda yakınsa long, üst banda yakınsa short
                if close < (bb_lower + (bb_upper - bb_lower) * 0.3):
                    long_score += 15 * self.strategy.get('bb_weight')
                    reasons.append("Fiyat daralan BB'nin alt kısmında")
                elif close > (bb_lower + (bb_upper - bb_lower) * 0.7):
                    short_score += 15 * self.strategy.get('bb_weight')
                    reasons.append("Fiyat daralan BB'nin üst kısmında")
            
            # BB genişleme sinyalleri
            if bb_width > bb_width_prev * 1.3:  # BB genişliyor
                reasons.append(f"Bollinger Bandı genişlemesi: {bb_width:.4f}")
                
                # Genişleme yönüne göre işlem yap
                if close > close_prev:
                    long_score += 10 * self.strategy.get('bb_weight')
                else:
                    short_score += 10 * self.strategy.get('bb_weight')
            
            # BB kenar testi sinyalleri
            if close_prev <= bb_lower and close > bb_lower:
                long_score += 20 * self.strategy.get('bb_weight')
                reasons.append("Fiyat BB alt bandını yukarı kırdı")
            elif close_prev >= bb_upper and close < bb_upper:
                short_score += 20 * self.strategy.get('bb_weight')
                reasons.append("Fiyat BB üst bandını aşağı kırdı")
            
            # EMA sinyalleri
            ema_short = df['ema_short'].iloc[last_idx]
            ema_medium = df['ema_medium'].iloc[last_idx]
            ema_long = df['ema_long'].iloc[last_idx]
            
            # EMA çapraz (golden/death cross) sinyalleri
            if df['ema_short'].iloc[last_idx - 1] < df['ema_medium'].iloc[last_idx - 1] and ema_short > ema_medium:
                long_score += 25 * self.strategy.get('ema_weight')
                reasons.append(f"EMA Golden Cross: {self.strategy.get('ema_short')} EMA > {self.strategy.get('ema_medium')} EMA")
            elif df['ema_short'].iloc[last_idx - 1] > df['ema_medium'].iloc[last_idx - 1] and ema_short < ema_medium:
                short_score += 25 * self.strategy.get('ema_weight')
                reasons.append(f"EMA Death Cross: {self.strategy.get('ema_short')} EMA < {self.strategy.get('ema_medium')} EMA")
            
            # EMA trend sinyalleri
            if ema_short > ema_medium > ema_long:
                long_score += 15 * self.strategy.get('ema_weight')
                reasons.append("EMA trend yapısı yükseliş gösteriyor")
            elif ema_short < ema_medium < ema_long:
                short_score += 15 * self.strategy.get('ema_weight')
                reasons.append("EMA trend yapısı düşüş gösteriyor")
            
            # Fiyatın EMA'lara göre pozisyonu
            if close > ema_short > ema_medium:
                long_score += 10 * self.strategy.get('ema_weight')
            elif close < ema_short < ema_medium:
                short_score += 10 * self.strategy.get('ema_weight')
            
            # Stochastic sinyalleri
            stoch_k = df['stoch_k'].iloc[last_idx]
            stoch_d = df['stoch_d'].iloc[last_idx]
            stoch_k_prev = df['stoch_k'].iloc[last_idx - 1]
            stoch_d_prev = df['stoch_d'].iloc[last_idx - 1]
            
            # Stochastic aşırı alım/satım durumları
            if stoch_k < self.strategy.get('stoch_oversold') and stoch_d < self.strategy.get('stoch_oversold'):
                long_score += 15 * self.strategy.get('stoch_weight')
                reasons.append(f"Stochastic aşırı satım bölgesinde: {stoch_k:.1f}/{stoch_d:.1f}")
            elif stoch_k > self.strategy.get('stoch_overbought') and stoch_d > self.strategy.get('stoch_overbought'):
                short_score += 15 * self.strategy.get('stoch_weight')
                reasons.append(f"Stochastic aşırı alım bölgesinde: {stoch_k:.1f}/{stoch_d:.1f}")
            
            # Stochastic kesişme sinyalleri
            if stoch_k_prev < stoch_d_prev and stoch_k > stoch_d:
                long_score += 20 * self.strategy.get('stoch_weight')
                reasons.append("Stochastic K çizgisi D çizgisini yukarı kesti")
            elif stoch_k_prev > stoch_d_prev and stoch_k < stoch_d:
                short_score += 20 * self.strategy.get('stoch_weight')
                reasons.append("Stochastic K çizgisi D çizgisini aşağı kesti")
            
            # ADX sinyalleri
            adx = df['adx'].iloc[last_idx]
            di_plus = df['di_plus'].iloc[last_idx]
            di_minus = df['di_minus'].iloc[last_idx]
            
            # Güçlü trend sinyalleri
            if adx > self.strategy.get('adx_threshold'):
                if di_plus > di_minus:
                    long_score += 20 * self.strategy.get('adx_weight')
                    reasons.append(f"Güçlü yükseliş trendi: ADX={adx:.1f}, +DI={di_plus:.1f}, -DI={di_minus:.1f}")
                else:
                    short_score += 20 * self.strategy.get('adx_weight')
                    reasons.append(f"Güçlü düşüş trendi: ADX={adx:.1f}, +DI={di_plus:.1f}, -DI={di_minus:.1f}")
            
            # DI kesişme sinyalleri
            if df['di_plus'].iloc[last_idx - 1] < df['di_minus'].iloc[last_idx - 1] and di_plus > di_minus:
                long_score += 15 * self.strategy.get('adx_weight')
                reasons.append("+DI -DI'yı yukarı kesti")
            elif df['di_plus'].iloc[last_idx - 1] > df['di_minus'].iloc[last_idx - 1] and di_plus < di_minus:
                short_score += 15 * self.strategy.get('adx_weight')
                reasons.append("+DI -DI'yı aşağı kesti")
            
            # Hacim indikatörleri sinyalleri
            obv = df['obv'].iloc[last_idx]
            obv_prev = df['obv'].iloc[last_idx - 1]
            vpt = df['vpt'].iloc[last_idx]
            vpt_prev = df['vpt'].iloc[last_idx - 1]
            
            # OBV sinyalleri
            if obv > obv_prev and (obv - obv_prev) / abs(obv_prev) > 0.01:  # %1'den fazla artış
                long_score += 10 * self.strategy.get('obv_weight')
                reasons.append("OBV artıyor")
            elif obv < obv_prev and (obv_prev - obv) / abs(obv_prev) > 0.01:  # %1'den fazla azalış
                short_score += 10 * self.strategy.get('obv_weight')
                reasons.append("OBV azalıyor")
            
            # VPT sinyalleri
            if vpt > vpt_prev and (vpt - vpt_prev) / abs(vpt_prev) > 0.01:  # %1'den fazla artış
                long_score += 10 * self.strategy.get('vpt_weight')
                reasons.append("VPT artıyor")
            elif vpt < vpt_prev and (vpt_prev - vpt) / abs(vpt_prev) > 0.01:  # %1'den fazla azalış
                short_score += 10 * self.strategy.get('vpt_weight')
                reasons.append("VPT azalıyor")
            
            # Ichimoku sinyalleri
            ichimoku_conv = df['ichimoku_conversion'].iloc[last_idx]
            ichimoku_base = df['ichimoku_base'].iloc[last_idx]
            ichimoku_a = df['ichimoku_a'].iloc[last_idx]
            ichimoku_b = df['ichimoku_b'].iloc[last_idx]
            
            # Tenkan-sen (conversion) ve Kijun-sen (base) kesişme sinyalleri
            if df['ichimoku_conversion'].iloc[last_idx - 1] < df['ichimoku_base'].iloc[last_idx - 1] and ichimoku_conv > ichimoku_base:
                long_score += 15 * self.strategy.get('ichimoku_weight')
                reasons.append("Ichimoku Tenkan-sen Kijun-sen'i yukarı kesti")
            elif df['ichimoku_conversion'].iloc[last_idx - 1] > df['ichimoku_base'].iloc[last_idx - 1] and ichimoku_conv < ichimoku_base:
                short_score += 15 * self.strategy.get('ichimoku_weight')
                reasons.append("Ichimoku Tenkan-sen Kijun-sen'i aşağı kesti")
            
            # Kumo (cloud) geçiş sinyalleri
            cloud_top = max(ichimoku_a, ichimoku_b)
            cloud_bottom = min(ichimoku_a, ichimoku_b)
            
            if df['close'].iloc[last_idx - 1] < cloud_bottom and close > cloud_bottom:
                long_score += 20 * self.strategy.get('ichimoku_weight')
                reasons.append("Fiyat Ichimoku bulutu üzerine çıktı")
            elif df['close'].iloc[last_idx - 1] > cloud_top and close < cloud_top:
                short_score += 20 * self.strategy.get('ichimoku_weight')
                reasons.append("Fiyat Ichimoku bulutu altına indi")
            
            # Kumo içinde veya dışında olma durumu
            if close > cloud_top:
                long_score += 10 * self.strategy.get('ichimoku_weight')
                reasons.append("Fiyat Ichimoku bulutu üzerinde")
            elif close < cloud_bottom:
                short_score += 10 * self.strategy.get('ichimoku_weight')
                reasons.append("Fiyat Ichimoku bulutu altında")
            
            # Piyasa durumuna göre sinyal uyarla
            self._adjust_signal_to_market_state(market_state, long_score, short_score, reasons, timeframe)
            
            # Zaman dilimine göre sinyal ağırlığını düzenle
            timeframe_weight = self._get_timeframe_weight_factor(timeframe)
            long_score *= timeframe_weight
            short_score *= timeframe_weight
            
            # Son sinyali oluştur ve döndür
            return {
                'long_score': long_score,
                'short_score': short_score,
                'reasons': reasons
            }
        except Exception as e:
            logger.error(f"{timeframe} için sinyaller hesaplanırken hata: {e}\n{traceback.format_exc()}")
            return {'long_score': 0, 'short_score': 0, 'reasons': [f"Hata: {str(e)}"]}
    
    def _adjust_signal_to_market_state(self, market_state: Dict, long_score: float, 
                                     short_score: float, reasons: List[str], timeframe: str):
        """Piyasa durumuna göre sinyal skorunu ayarlar."""
        # Piyasa eğilimi
        trend_score = market_state.get('trend_score', 0)
        
        # Eğilim uyumlu sinyalleri güçlendir, ters sinyalleri zayıflat
        if trend_score > 30:  # Yükselen piyasa
            long_score *= 1.2
            short_score *= 0.8
            reasons.append(f"Yükselen piyasada long sinyaller güçlendirildi: {trend_score:.1f}")
        elif trend_score < -30:  # Düşen piyasa
            long_score *= 0.8
            short_score *= 1.2
            reasons.append(f"Düşen piyasada short sinyaller güçlendirildi: {trend_score:.1f}")
        
        # Volatilite durumu
        volatility_score = market_state.get('volatility_score', 1.0)
        volatility_state = market_state.get('volatility_state', 'MODERATE')
        
        # Yüksek volatilitede sinyal eşiğini yükselt, düşük volatilitede düşür
        if volatility_state == 'HIGH' or volatility_state == 'EXTREME':
            # Kısa zaman dilimlerinde aşırı volatilitede sinyal kalitesi düşer
            if timeframe in ['1m', '3m', '5m', '15m']:
                long_score *= 0.8
                short_score *= 0.8
                reasons.append(f"Yüksek volatilitede kısa vadeli sinyaller zayıflatıldı: {volatility_score:.1f}")
            else:
                reasons.append(f"Yüksek volatilite: {volatility_score:.1f}")
        elif volatility_state == 'LOW':
            # Düşük volatilitede uzun zaman dilimlerini tercih et
            if timeframe in ['4h', '1d', '3d']:
                long_score *= 1.2
                short_score *= 1.2
                reasons.append(f"Düşük volatilitede uzun vadeli sinyaller güçlendirildi: {volatility_score:.1f}")
            else:
                reasons.append(f"Düşük volatilite: {volatility_score:.1f}")
    
    def _get_timeframe_weight_factor(self, timeframe: str) -> float:
        """Zaman dilimine göre ağırlık faktörü döndürür."""
        # Genel ağırlıklar
        weights = {
            '1m': 0.4, '3m': 0.5, '5m': 0.6, '15m': 0.7, '30m': 0.8,
            '1h': 0.9, '2h': 0.95, '4h': 1.0, '6h': 1.05, '8h': 1.1,
            '12h': 1.15, '1d': 1.2, '3d': 1.25, '1w': 1.3
        }
        
        # Primary timeframe için ağırlığı artır
        if timeframe == self.strategy.get('primary_timeframe'):
            return weights.get(timeframe, 1.0) * 1.5
        
        return weights.get(timeframe, 1.0)
    
    def _extract_key_indicators(self, df: pd.DataFrame) -> Dict:
        """Son muma ait önemli göstergeleri çıkarır."""
        if df is None or len(df) < 1:
            return {}
        
        last_idx = len(df) - 1
        
        try:
            return {
                'close': float(df['close'].iloc[last_idx]),
                'open': float(df['open'].iloc[last_idx]),
                'high': float(df['high'].iloc[last_idx]),
                'low': float(df['low'].iloc[last_idx]),
                'volume': float(df['volume'].iloc[last_idx]),
                'rsi': float(df['rsi'].iloc[last_idx]),
                'macd': float(df['macd'].iloc[last_idx]),
                'macd_signal': float(df['macd_signal'].iloc[last_idx]),
                'macd_histogram': float(df['macd_histogram'].iloc[last_idx]),
                'ema_short': float(df['ema_short'].iloc[last_idx]),
                'ema_medium': float(df['ema_medium'].iloc[last_idx]),
                'ema_long': float(df['ema_long'].iloc[last_idx]),
                'bb_upper': float(df['bb_upper'].iloc[last_idx]),
                'bb_middle': float(df['bb_middle'].iloc[last_idx]),
                'bb_lower': float(df['bb_lower'].iloc[last_idx]),
                'atr': float(df['atr'].iloc[last_idx]),
                'adx': float(df['adx'].iloc[last_idx])
            }
        except Exception as e:
            logger.error(f"Göstergeler çıkarılırken hata: {e}")
            return {}
    
    def _detect_consolidation(self, df: pd.DataFrame) -> bool:
        """Fiyat konsolidasyonu (sıkışma) tespiti yapar."""
        if df is None or len(df) < 20:
            return False
        
        try:
            # Son 10 mumda Bollinger Bandı daralması
            bb_width = df['bb_width'].iloc[-10:].mean()
            bb_width_prev = df['bb_width'].iloc[-20:-10].mean()
            
            # BB genişliği daraldı mı?
            if bb_width < bb_width_prev * 0.8:
                # ATR düşüş kontrolü
                atr = df['atr'].iloc[-10:].mean()
                atr_prev = df['atr'].iloc[-20:-10].mean()
                
                if atr < atr_prev * 0.8:
                    return True
            
            return False
        except Exception as e:
            logger.error(f"Konsolidasyon tespitinde hata: {e}")
            return False
    
    def _detect_divergence(self, df: pd.DataFrame) -> Optional[Dict]:
        """RSI ve fiyat arasındaki uyumsuzlukları (divergence) tespit eder."""
        if df is None or len(df) < 30:
            return None
        
        try:
            # Son 30 mumda yerel maksimum ve minimum noktaları bul
            local_max_prices = []
            local_max_rsi = []
            local_min_prices = []
            local_min_rsi = []
            
            price_data = df['close'].iloc[-30:].values
            rsi_data = df['rsi'].iloc[-30:].values
            
            # Yerel maksimumlar
            for i in range(1, len(price_data) - 1):
                # Fiyat yerel maksimum
                if price_data[i] > price_data[i-1] and price_data[i] > price_data[i+1]:
                    local_max_prices.append((i, price_data[i]))
                
                # RSI yerel maksimum
                if rsi_data[i] > rsi_data[i-1] and rsi_data[i] > rsi_data[i+1]:
                    local_max_rsi.append((i, rsi_data[i]))
            
            # Yerel minimumlar
            for i in range(1, len(price_data) - 1):
                # Fiyat yerel minimum
                if price_data[i] < price_data[i-1] and price_data[i] < price_data[i+1]:
                    local_min_prices.append((i, price_data[i]))
                
                # RSI yerel minimum
                if rsi_data[i] < rsi_data[i-1] and rsi_data[i] < rsi_data[i+1]:
                    local_min_rsi.append((i, rsi_data[i]))
            
            # En az iki yerel maksimum/minimum yoksa divergence yok
            if len(local_max_prices) < 2 or len(local_max_rsi) < 2 or len(local_min_prices) < 2 or len(local_min_rsi) < 2:
                return None
            
            # Son iki yerel maksimum kontrol et - bearish divergence
            if (len(local_max_prices) >= 2 and len(local_max_rsi) >= 2 and
                local_max_prices[-1][1] > local_max_prices[-2][1] and
                local_max_rsi[-1][1] < local_max_rsi[-2][1]):
                return {
                    "type": "BEARISH",
                    "strength": abs(local_max_rsi[-1][1] - local_max_rsi[-2][1]) / local_max_rsi[-2][1] * 100
                }
            
            # Son iki yerel minimum kontrol et - bullish divergence
            if (len(local_min_prices) >= 2 and len(local_min_rsi) >= 2 and
                local_min_prices[-1][1] < local_min_prices[-2][1] and
                local_min_rsi[-1][1] > local_min_rsi[-2][1]):
                return {
                    "type": "BULLISH",
                    "strength": abs(local_min_rsi[-1][1] - local_min_rsi[-2][1]) / local_min_rsi[-2][1] * 100
                }
            
            return None
        except Exception as e:
            logger.error(f"Divergence tespitinde hata: {e}")
            return None
    
    async def _check_funding_rate(self, symbol: str) -> float:
        """Funding rate kontrolü yapar."""
        try:
            funding_rate = await self.market_data.client.get_funding_rate(symbol)
            
            # Funding rate kontrolü yap
            if self.strategy.get('avoid_high_funding'):
                threshold = self.strategy.get('funding_rate_threshold')
                
                # Pozitif funding rate short için, negatif funding rate long için uygun
                if funding_rate > threshold:
                    logger.info(f"{symbol} yüksek pozitif funding rate: {funding_rate:.6f}, short tercih edilebilir")
                    
                    # UI aktivite loguna ekle
                    if hasattr(self.market_data, 'ui') and self.market_data.ui:
                        self.market_data.ui.log_activity(
                            f"{symbol} yüksek pozitif funding rate: {funding_rate:.6f}",
                            "INFO",
                            {"symbol": symbol, "funding_rate": funding_rate, "suggestion": "SHORT"}
                        )
                        
                elif funding_rate < -threshold:
                    logger.info(f"{symbol} yüksek negatif funding rate: {funding_rate:.6f}, long tercih edilebilir")
                    
                    # UI aktivite loguna ekle
                    if hasattr(self.market_data, 'ui') and self.market_data.ui:
                        self.market_data.ui.log_activity(
                            f"{symbol} yüksek negatif funding rate: {funding_rate:.6f}",
                            "INFO",
                            {"symbol": symbol, "funding_rate": funding_rate, "suggestion": "LONG"}
                        )
            
            return funding_rate
        except Exception as e:
            logger.error(f"{symbol} funding rate kontrolünde hata: {e}")
            return 0.0
    
    def _is_signal_tradable(self, signal_type: str, signal_strength: float, 
                          timing_score: float, market_state: Dict, 
                          funding_rate: float) -> bool:
        """Sinyal işlem yapılabilir mi kontrol eder."""
        # Minimum sinyal gücü kontrolü
        if signal_strength < self.strategy.get('min_score_to_trade'):
            return False
        
        # Giriş zamanlama puanı kontrolü
        if timing_score < 50:  # 50/100 altında zayıf zamanlama
            logger.debug(f"Zamanlama puanı düşük: {timing_score:.1f}/100")
            return False
        
        # İşlem tipine göre eşik kontrol et
        if signal_type == "LONG":
            if signal_strength < self.strategy.get('score_threshold_long'):
                return False
            
            # Trading type kontrolü
            if self.strategy.get('trading_type') == 'SHORT_ONLY':
                return False
            
            # Düşen piyasada long sinyallerini sık
            if market_state['market_state'] in ['BEARISH', 'SLIGHTLY_BEARISH']:
                if signal_strength < self.strategy.get('score_threshold_long') * 1.2:
                    return False
            
            # Funding rate kontrolü (pozitif funding rate long'a karşı)
            if self.strategy.get('avoid_high_funding') and funding_rate > self.strategy.get('funding_rate_threshold'):
                # Sinyal çok güçlü değilse, funding rate nedeniyle işlem yapma
                if signal_strength < self.strategy.get('score_threshold_long') * 1.5:
                    return False
        
        elif signal_type == "SHORT":
            if signal_strength < self.strategy.get('score_threshold_short'):
                return False
            
            # Trading type kontrolü
            if self.strategy.get('trading_type') == 'LONG_ONLY':
                return False
            
            # Yükselen piyasada short sinyallerini sık
            if market_state['market_state'] in ['BULLISH', 'SLIGHTLY_BULLISH']:
                if signal_strength < self.strategy.get('score_threshold_short') * 1.2:
                    return False
            
            # Funding rate kontrolü (negatif funding rate short'a karşı)
            if self.strategy.get('avoid_high_funding') and funding_rate < -self.strategy.get('funding_rate_threshold'):
                # Sinyal çok güçlü değilse, funding rate nedeniyle işlem yapma
                if signal_strength < self.strategy.get('score_threshold_short') * 1.5:
                    return False
        
        return True