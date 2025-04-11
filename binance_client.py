"""
Binance API istemcisi
"""

import os
import time
import json
import asyncio
import logging
import traceback
import aiofiles
import concurrent.futures
import certifi
from functools import wraps
from typing import Dict, List, Tuple, Optional, Union
from datetime import datetime

import aiohttp
import numpy as np
from binance.client import Client
from binance.enums import *
from binance.exceptions import BinanceAPIException

from trading_bot.api.exceptions import (
    CustomError, NetworkError, APIError, AccountError, InputError
)

logger = logging.getLogger("trading_bot")
api_logger = logging.getLogger("api_calls")
perf_logger = logging.getLogger("performance")

def timer_decorator(func):
    """Bir işlevin çalışma süresini ölçen decorator"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        func_name = func.__name__
        try:
            result = await func(*args, **kwargs)
            elapsed = time.time() - start_time
            perf_logger.debug(f"İşlev {func_name} {elapsed:.4f} saniyede tamamlandı")
            return result
        except Exception as e:
            elapsed = time.time() - start_time
            perf_logger.error(f"İşlev {func_name} {elapsed:.4f} saniyede hata verdi: {e}")
            raise
    return wrapper

def exception_handler(func):
    """İstisnaları ele alan ve loglayan decorator"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except (BinanceAPIException, aiohttp.ClientError) as e:
            api_logger.error(f"API/Ağ hatası: {func.__name__}: {e}")
            raise NetworkError(f"API/Ağ hatası: {str(e)}")
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.error(f"Veri işleme hatası: {func.__name__}: {e}")
            raise InputError(f"Veri işleme hatası: {str(e)}")
        except Exception as e:
            logger.error(f"Beklenmedik hata: {func.__name__}: {e}\n{traceback.format_exc()}")
            raise CustomError(f"Beklenmedik hata: {str(e)}")
    return wrapper

class BinanceClient:
    """Binance API wrapper sınıfı."""
    
    def __init__(self, api_key: str, api_secret: str, testnet=False, max_retries=5):
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.max_retries = max_retries
        self._client = None
        self._lock = asyncio.Lock()  # API çağrıları için senkronizasyon lock'u
        self._client_session = None
        self._symbol_info_cache = {}  # Sembol bilgilerini önbellekleme
        self.last_api_call_time = 0
        self.min_time_between_calls = 0.05  # 50ms - API çağrıları arasındaki minimum süre
        self._leverage_cache = {}  # Sembol bazında kaldıraç bilgisini önbellekleme
    
    @property
    def client(self):
        """Lazy loading ile client'ı oluşturur."""
        if self._client is None:
            self._client = Client(self.api_key, self.api_secret, testnet=self.testnet)
        return self._client
    
    async def close(self):
        """Tüm kaynakları serbest bırakır."""
        if self._client_session:
            await self._client_session.close()
            self._client_session = None
    
    @exception_handler
    @timer_decorator
    async def api_retry(self, func, *args, **kwargs):
        """API çağrılarını yeniden deneme mekanizmasıyla çalıştırır."""
        func_name = func.__name__
        start_time = time.time()
        
        # Hız sınırlama kontrolü
        time_since_last_call = time.time() - self.last_api_call_time
        if time_since_last_call < self.min_time_between_calls:
            await asyncio.sleep(self.min_time_between_calls - time_since_last_call)
        
        # API çağrılarını eşzamanlama için Lock kullan
        async with self._lock:
            for attempt in range(1, self.max_retries + 1):
                try:
                    api_logger.debug(f"API çağrısı başlatılıyor: {func_name}, Deneme={attempt}")
                    
                    # Asenkron executor ile senkron çağrıları yönet
                    loop = asyncio.get_running_loop()
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        result = await loop.run_in_executor(
                            pool, lambda: func(*args, **kwargs)
                        )
                    
                    elapsed = time.time() - start_time
                    api_logger.info(f"API çağrısı başarılı: {func_name}, Süre={elapsed:.3f}s")
                    
                    # Son API çağrı zamanını güncelle
                    self.last_api_call_time = time.time()
                    
                    return result
                except BinanceAPIException as e:
                    elapsed = time.time() - start_time
                    error_code = getattr(e, 'code', None)
                    api_logger.warning(
                        f"API Hatası: {func_name}, Deneme={attempt}/{self.max_retries}, "
                        f"Kod={error_code}, Hata={e}, Süre={elapsed:.3f}s"
                    )
                    
                    # Hata tipine göre işlem yap
                    if error_code in [-1021, -1022]:  # Timestamp hatası
                        # Saat senkronizasyon hatası, hemen yeniden dene
                        continue
                    elif error_code == -1003:  # Ağırlık sınırı aşıldı
                        wait_time = 2 ** attempt * 2  # Daha uzun bekleme süresi
                        api_logger.info(f"Ağırlık sınırı aşıldı, {wait_time} saniye bekleniyor")
                        await asyncio.sleep(wait_time)
                    elif error_code == -2010:  # Yetersiz bakiye
                        logger.error(f"Yetersiz bakiye hatası: {e}")
                        raise AccountError(f"Yetersiz bakiye: {str(e)}")
                    elif error_code == -2011:  # Bilinmeyen emir hatası
                        logger.error(f"Emir hatası: {e}")
                        raise APIError(f"Emir hatası: {str(e)}")
                    elif error_code == -1121:  # Geçersiz sembol
                        raise InputError(f"Geçersiz sembol: {str(e)}")
                    else:
                        # Diğer API hataları için exponential backoff
                        if attempt < self.max_retries:
                            wait_time = 2 ** attempt
                            api_logger.info(f"Yeniden deneme bekleniyor: {wait_time} saniye")
                            await asyncio.sleep(wait_time)
                        else:
                            error_msg = f"API hatası: {func_name} başarısız oldu. Hata: {e}"
                            api_logger.error(
                                f"API çağrısı başarısız: {func_name}, "
                                f"{self.max_retries} denemeden sonra vazgeçildi. Hata: {e}"
                            )
                            raise APIError(f"API hatası: {str(e)}")
                except Exception as e:
                    elapsed = time.time() - start_time
                    api_logger.error(
                        f"Beklenmeyen hata: {func_name}, Deneme={attempt}/{self.max_retries}, "
                        f"Hata={e}, Süre={elapsed:.3f}s"
                    )
                    
                    if attempt < self.max_retries:
                        wait_time = 2 ** attempt
                        api_logger.info(f"Yeniden deneme bekleniyor: {wait_time} saniye")
                        await asyncio.sleep(wait_time)
                    else:
                        error_msg = f"Beklenmeyen hata: {func_name} başarısız oldu. Hata: {e}"
                        detailed_error = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
                        api_logger.error(f"Detaylı hata: {detailed_error}")
                        raise CustomError(f"Beklenmeyen hata: {str(e)}")
    
    @exception_handler
    async def get_futures_market_data(self):
        """Vadeli işlemler piyasa verilerini alır ve önbelleğe kaydeder."""
        cache_file = f"./data/cache/futures_market_data.json"
        cache_expiry = 3600  # 1 saat
        
        # Önbellek kontrolü
        try:
            if os.path.exists(cache_file):
                file_age = time.time() - os.path.getmtime(cache_file)
                if file_age < cache_expiry:
                    async with aiofiles.open(cache_file, 'r') as f:
                        return json.loads(await f.read())
        except Exception as e:
            logger.warning(f"Önbellek okuma hatası: {e}")
        
        # Yeni veri al
        market_data = await self.api_retry(self.client.futures_exchange_info)
        
        # Önbelleğe kaydet (asenkron olarak)
        try:
            async with aiofiles.open(cache_file, 'w') as f:
                await f.write(json.dumps(market_data))
        except Exception as e:
            logger.warning(f"Önbellek yazma hatası: {e}")
        
        return market_data
    
    @exception_handler
    async def get_symbol_precision(self, symbol: str) -> Dict:
        """Sembol için fiyat ve miktar hassasiyetini alır."""
        # Önbellek kontrolü
        if symbol in self._symbol_info_cache:
            return self._symbol_info_cache[symbol]
        
        market_data = await self.get_futures_market_data()
        symbol_info = next((s for s in market_data['symbols'] if s['symbol'] == symbol), None)
        
        if not symbol_info:
            raise InputError(f"Sembol bulunamadı: {symbol}")
        
        price_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'PRICE_FILTER'), None)
        lot_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
        min_notional = next((f for f in symbol_info['filters'] if f['filterType'] == 'MIN_NOTIONAL'), None)
        
        price_precision = abs(int(np.log10(float(price_filter['tickSize'])))) if price_filter else 0
        qty_precision = abs(int(np.log10(float(lot_filter['stepSize'])))) if lot_filter else 0
        
        result = {
            'price_precision': price_precision,
            'qty_precision': qty_precision,
            'min_qty': float(lot_filter['minQty']) if lot_filter else 0,
            'tick_size': float(price_filter['tickSize']) if price_filter else 0,
            'min_notional': float(min_notional['notional']) if min_notional else 5.0,
            'base_asset': symbol_info['baseAsset'],
            'quote_asset': symbol_info['quoteAsset'],
            'symbol': symbol
        }
        
        # Önbelleğe kaydet
        self._symbol_info_cache[symbol] = result
        
        return result
    
    @exception_handler
    async def get_account_balance(self) -> Dict:
        """Hesap bakiyesini alır."""
        account_info = await self.api_retry(self.client.futures_account)
        
        balances = {}
        for asset in account_info['assets']:
            symbol = asset['asset']
            balances[symbol] = {
                'wallet_balance': float(asset['walletBalance']),
                'unrealized_pnl': float(asset['unrealizedProfit']),
                'margin_balance': float(asset['marginBalance']),
                'available_balance': float(asset['availableBalance']),
                'max_withdraw_amount': float(asset['maxWithdrawAmount'])
            }
        
        return balances
    
    # Senkron olarak mark_price alma metodu (UI için)
    def _sync_get_mark_price(self, symbol: str) -> float:
        """Sembol için güncel işaretleme fiyatını senkron olarak alır (UI için)."""
        try:
            mark_price_info = self.client.futures_mark_price(symbol=symbol)
            
            if isinstance(mark_price_info, list):
                mark_price_info = mark_price_info[0]
            
            return float(mark_price_info['markPrice'])
        except Exception as e:
            logger.debug(f"Güncel fiyat senkron olarak alınamadı: {e}")
            return 0
    
    @exception_handler
    async def get_leverage_for_symbol(self, symbol: str) -> int:
        """Sembol için ayarlanmış kaldıraç bilgisini alır."""
        # Önbellekte kontrol et
        if symbol in self._leverage_cache:
            return self._leverage_cache[symbol]
        
        try:
            # Kaldıraç bilgisini API'den al
            leverage_info = await self.api_retry(self.client.futures_leverage_bracket, symbol=symbol)
            
            # Bilgiyi işle ve önbelleğe al
            if leverage_info and len(leverage_info) > 0:
                current_leverage = int(leverage_info[0].get('initialLeverage', 1))
                self._leverage_cache[symbol] = current_leverage
                return current_leverage
        except Exception as e:
            logger.warning(f"{symbol} için kaldıraç bilgisi alınamadı: {e}")
        
        # Varsayılan değer döndür
        return 1  # Varsayılan kaldıraç 1x
    
    @exception_handler
    async def get_open_positions(self) -> List[Dict]:
        """Açık pozisyonları alır."""
        try:
            positions = await self.api_retry(self.client.futures_position_information)
            
            active_positions = []
            for pos in positions:
                if float(pos.get('positionAmt', '0')) != 0:
                    try:
                        # Pozisyon miktarı
                        position_amt = float(pos.get('positionAmt', '0'))
                        
                        # Temel pozisyon bilgileri - güvenli şekilde al
                        symbol = pos.get('symbol', '')
                        entry_price = float(pos.get('entryPrice', '0'))
                        mark_price = float(pos.get('markPrice', '0'))
                        unrealized_profit = float(pos.get('unRealizedProfit', '0'))
                        margin_type = pos.get('marginType', 'isolated')
                        isolated_margin = float(pos.get('isolatedMargin', '0')) if margin_type == 'isolated' else 0
                        
                        # Kaldıraç bilgisi - özel işleme
                        leverage = None
                        
                        # 1. Doğrudan API yanıtından almayı dene
                        if 'leverage' in pos:
                            try:
                                leverage = int(pos['leverage'])
                            except (ValueError, TypeError):
                                leverage = None
                        
                        # 2. Önbellekte kontrol et
                        if leverage is None and symbol in self._leverage_cache:
                            leverage = self._leverage_cache[symbol]
                        
                        # 3. API ile almayı dene
                        if leverage is None:
                            try:
                                leverage = await self.get_leverage_for_symbol(symbol)
                            except Exception as e:
                                logger.warning(f"{symbol} için kaldıraç bilgisi alınamadı: {e}")
                                leverage = 1  # Varsayılan
                        
                        # Pozisyon bilgilerini oluştur
                        position_data = {
                            'symbol': symbol,
                            'amount': position_amt,
                            'entry_price': entry_price,
                            'mark_price': mark_price,
                            'pnl': unrealized_profit,
                            'leverage': leverage,
                            'margin_type': margin_type,
                            'isolated_margin': isolated_margin,
                            'side': 'LONG' if position_amt > 0 else 'SHORT'
                        }
                        
                        active_positions.append(position_data)
                        
                    except Exception as e:
                        logger.error(f"Pozisyon verisi işlenirken hata: {e} - {pos}")
                        continue
            
            return active_positions
            
        except Exception as e:
            logger.error(f"Açık pozisyonlar alınırken hata: {e}")
            return []
    
    @exception_handler
    async def set_leverage(self, symbol: str, leverage: int) -> Dict:
        """Kaldıraç seviyesini ayarlar."""
        result = await self.api_retry(self.client.futures_change_leverage, symbol=symbol, leverage=leverage)
        
        # Kaldıraç önbelleğini güncelle
        if result and 'leverage' in result:
            self._leverage_cache[symbol] = int(result['leverage'])
        
        return result
    
    @exception_handler
    async def set_margin_type(self, symbol: str, margin_type: str) -> Dict:
        """Margin tipini ayarlar (ISOLATED/CROSSED)."""
        try:
            return await self.api_retry(
                self.client.futures_change_margin_type,
                symbol=symbol,
                marginType=margin_type
            )
        except BinanceAPIException as e:
            # Zaten doğru margin tipindeyse hata fırlatır, bu normal
            if "No need to change margin type" in str(e):
                return {"msg": "Already set to requested margin type"}
            raise
    
    @exception_handler
    async def create_market_order(self, symbol: str, side: str, quantity: float, reduce_only=False) -> Dict:
        """Market emri oluşturur."""
        params = {
            'symbol': symbol,
            'side': side,
            'type': ORDER_TYPE_MARKET,
            'quantity': quantity
        }
        
        if reduce_only:
            params['reduceOnly'] = 'true'
        
        return await self.api_retry(self.client.futures_create_order, **params)
    
    @exception_handler
    async def create_limit_order(self, symbol: str, side: str, quantity: float, 
                               price: float, time_in_force='GTC', reduce_only=False) -> Dict:
        """Limit emri oluşturur."""
        params = {
            'symbol': symbol,
            'side': side,
            'type': ORDER_TYPE_LIMIT,
            'quantity': quantity,
            'price': price,
            'timeInForce': time_in_force
        }
        
        if reduce_only:
            params['reduceOnly'] = 'true'
        
        return await self.api_retry(self.client.futures_create_order, **params)
    
    @exception_handler
    async def create_stop_market_order(self, symbol: str, side: str, quantity: float, 
                                     stop_price: float, reduce_only=True) -> Dict:
        """Stop market emri oluşturur."""
        params = {
            'symbol': symbol,
            'side': side,
            'type': FUTURE_ORDER_TYPE_STOP_MARKET,
            'quantity': quantity,
            'stopPrice': stop_price
        }
        
        if reduce_only:
            params['reduceOnly'] = 'true'
        
        return await self.api_retry(self.client.futures_create_order, **params)
    
    @exception_handler
    async def create_take_profit_market_order(self, symbol: str, side: str, quantity: float, 
                                            stop_price: float, reduce_only=True) -> Dict:
        """Take profit market emri oluşturur."""
        params = {
            'symbol': symbol,
            'side': side,
            'type': FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET,
            'quantity': quantity,
            'stopPrice': stop_price
        }
        
        if reduce_only:
            params['reduceOnly'] = 'true'
        
        return await self.api_retry(self.client.futures_create_order, **params)
    
    @exception_handler
    async def create_trailing_stop_order(self, symbol: str, side: str, quantity: float, 
                                       activation_price: float, callback_rate: float) -> Dict:
        """Trailing stop emri oluşturur."""
        params = {
            'symbol': symbol,
            'side': side,
            'type': FUTURE_ORDER_TYPE_TRAILING_STOP_MARKET,
            'quantity': quantity,
            'activationPrice': activation_price,
            'callbackRate': callback_rate,
            'reduceOnly': 'true'
        }
        
        return await self.api_retry(self.client.futures_create_order, **params)
    
    @exception_handler
    async def cancel_all_open_orders(self, symbol: str) -> Dict:
        """Sembol için tüm açık emirleri iptal eder."""
        return await self.api_retry(self.client.futures_cancel_all_open_orders, symbol=symbol)
    
    @exception_handler
    async def get_all_orders(self, symbol: str, limit=100) -> List[Dict]:
        """Emir geçmişini alır."""
        return await self.api_retry(self.client.futures_get_all_orders, symbol=symbol, limit=limit)
    
    @exception_handler
    async def get_open_orders(self, symbol: str = None) -> List[Dict]:
        """Açık emirleri alır."""
        params = {}
        if symbol:
            params["symbol"] = symbol
        
        return await self.api_retry(self.client.futures_get_open_orders, **params)
    
    @exception_handler
    async def get_funding_rate(self, symbol: str) -> float:
        """Sembol için güncel funding rate."""
        funding_info = await self.api_retry(self.client.futures_funding_rate, symbol=symbol, limit=1)
        
        if not funding_info:
            return 0.0
        
        return float(funding_info[0]['fundingRate'])
    
    @exception_handler
    async def get_mark_price(self, symbol: str) -> float:
        """Sembol için güncel işaretleme fiyatını alır."""
        mark_price_info = await self.api_retry(self.client.futures_mark_price, symbol=symbol)
        
        if isinstance(mark_price_info, list):
            mark_price_info = mark_price_info[0]
        
        return float(mark_price_info['markPrice'])
    
    @exception_handler
    async def get_historical_klines(self, symbol: str, interval: str, 
                                  start_time: int = None, end_time: int = None, 
                                  limit: int = 500) -> List[List]:
        """Tarihsel kline verileri alır."""
        # Kline verilerini önbelleğe almak için dosya adı oluştur
        cache_key = f"{symbol}_{interval}_{start_time}_{end_time}_{limit}"
        cache_filename = f"./data/cache/klines_{hash(cache_key)}.json"
        cache_expiry = 300  # 5 dakika
        
        # Önbellek kontrolü
        try:
            if os.path.exists(cache_filename):
                file_age = time.time() - os.path.getmtime(cache_filename)
                if file_age < cache_expiry:
                    async with aiofiles.open(cache_filename, 'r') as f:
                        return json.loads(await f.read())
        except Exception as e:
            logger.warning(f"Kline önbellek okuma hatası: {e}")
        
        # Parametreleri hazırla
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': limit
        }
        
        if start_time:
            params['startTime'] = start_time
        
        if end_time:
            params['endTime'] = end_time
        
        # API çağrısı
        klines = await self.api_retry(self.client.futures_klines, **params)
        
        # Önbelleğe kaydet
        try:
            async with aiofiles.open(cache_filename, 'w') as f:
                await f.write(json.dumps(klines))
        except Exception as e:
            logger.warning(f"Kline önbellek yazma hatası: {e}")
        
        return klines
    
    @exception_handler
    async def get_ticker_24h(self, symbol: str = None) -> Union[Dict, List[Dict]]:
        """24 saatlik ticker bilgilerini alır."""
        params = {}
        if symbol:
            params["symbol"] = symbol
        
        return await self.api_retry(self.client.futures_ticker, **params)
    
    @exception_handler
    async def get_top_volume_symbols(self, quote_asset='USDT', limit=20) -> List[Dict]:
        """En yüksek hacimli sembolleri döndürür."""
        all_tickers = await self.get_ticker_24h()
        
        # Quote asset'e göre filtreleme
        filtered_tickers = [
            ticker for ticker in all_tickers 
            if ticker['symbol'].endswith(quote_asset)
        ]
        
        # Hacme göre sıralama
        sorted_tickers = sorted(
            filtered_tickers, 
            key=lambda x: float(x['quoteVolume']), 
            reverse=True
        )
        
        return sorted_tickers[:limit]
    
    @exception_handler
    async def get_exchange_info(self) -> Dict:
        """Borsa bilgilerini alır."""
        return await self.api_retry(self.client.futures_exchange_info)
    
    @exception_handler
    async def get_income_history(self, income_type=None, start_time=None, end_time=None, limit=1000) -> List[Dict]:
        """Hesap gelir geçmişini alır."""
        params = {'limit': limit}
        
        if income_type:
            params['incomeType'] = income_type
        
        if start_time:
            params['startTime'] = start_time
        
        if end_time:
            params['endTime'] = end_time
        
        return await self.api_retry(self.client.futures_income_history, **params)