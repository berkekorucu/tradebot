"""
Position management and order creation module
"""

import asyncio
import logging
import traceback
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from trading_bot.api.binance_client import BinanceClient
from trading_bot.core.risk import RiskManager
from trading_bot.core.strategy import StrategyParams

logger = logging.getLogger("trading_bot")
trade_logger = logging.getLogger("trade_log")

class PositionManager:
    """Pozisyon yönetimi ve emir oluşturma sınıfı."""
    
    def __init__(self, client: BinanceClient, risk_manager: RiskManager, strategy: StrategyParams):
        self.client = client
        self.risk_manager = risk_manager
        self.strategy = strategy
        self.active_trades = {}  # {symbol: trade_info}
        self.stop_orders = {}  # {symbol: stop_order_info}
        self.take_profit_orders = {}  # {symbol: [tp_order_info]}
        self.position_lock = asyncio.Lock()  # Pozisyon işlemleri için lock
        self.ui = None  # UI referansı için alan
    
    async def open_position(self, symbol: str, signal_type: str, signal_strength: float, market_volatility: float = 1.0):
        """Yeni bir pozisyon açar."""
        async with self.position_lock:
            try:
                # Risk limitlerini kontrol et
                if not await self.risk_manager.check_risk_limits():
                    logger.warning(f"{symbol} için yeni pozisyon açılamadı: Risk limitleri aşıldı")
                    return None
                
                # Sembolde zaten açık pozisyon var mı kontrol et
                existing_position = self.risk_manager.get_position_for_symbol(symbol)
                if existing_position:
                    # Aynı yönde pozisyon varsa pozisyonu artırma
                    if (existing_position['side'] == "LONG" and signal_type == "LONG") or \
                       (existing_position['side'] == "SHORT" and signal_type == "SHORT"):
                        logger.info(f"{symbol} için zaten {existing_position['side']} pozisyonu var")
                        return existing_position
                    
                    # Ters yönde pozisyon varsa önce kapat
                    await self.close_position(symbol, "Ters sinyal, pozisyon yönü değiştiriliyor")
                
                # Güncel fiyatı al
                current_price = await self.client.get_mark_price(symbol)
                
                # API'den güncel fiyat alınamadıysa işlemi iptal et
                if current_price <= 0:
                    logger.warning(f"{symbol} için güncel fiyat alınamadı")
                    return None
                
                # Stop loss hesapla
                stop_loss_price = await self.risk_manager.calculate_stop_loss(
                    symbol, current_price, signal_type, market_volatility
                )
                
                # Pozisyon boyutu ve kaldıracı hesapla
                quantity, leverage = await self.risk_manager.calculate_position_size(
                    symbol, current_price, stop_loss_price, signal_type, signal_strength
                )
                
                if quantity <= 0:
                    logger.warning(f"{symbol} için geçersiz pozisyon boyutu: {quantity}")
                    return None
                
                # Margin tipini ayarla
                margin_type = self.strategy.get('margin_type')
                margin_set = await self.client.set_margin_type(symbol, margin_type)
                
                if not margin_set:
                    logger.warning(f"{symbol} için margin tipi ayarlanamadı")
                    # Devam et, bazı durumlarda zaten ayarlanmış olabilir
                
                # Kaldıracı ayarla
                leverage_set = await self.client.set_leverage(symbol, leverage)
                
                if not leverage_set:
                    logger.warning(f"{symbol} için kaldıraç ayarlanamadı: {leverage}x")
                    # Devam et, bazı durumlarda zaten ayarlanmış olabilir
                
                # Alım/satım yönünü belirle
                if signal_type == "LONG":
                    side = "BUY"
                    reduce_side = "SELL"
                else:  # SHORT
                    side = "SELL"
                    reduce_side = "BUY"
                
                # Market emri oluştur
                order_result = await self.client.create_market_order(symbol, side, quantity)
                
                if not order_result:
                    logger.error(f"{symbol} için market emri başarısız")
                    return None
                
                # Ortalama giriş fiyatını al
                filled_price = float(order_result.get('avgPrice', current_price))
                filled_qty = float(order_result.get('executedQty', quantity))
                
                # İşlemi kaydet
                trade_info = self.risk_manager.record_trade(
                    symbol, side, filled_qty, filled_price, trade_type="OPEN"
                )
                
                # Active trades listesine ekle
                self.active_trades[symbol] = {
                    'symbol': symbol,
                    'side': signal_type,
                    'quantity': filled_qty,
                    'entry_price': filled_price,
                    'leverage': leverage,
                    'stop_loss': stop_loss_price,
                    'signal_strength': signal_strength,
                    'open_time': datetime.now(),
                    'order_id': order_result.get('orderId')
                }
                
                # Stop-loss emrini oluştur
                stop_order = await self.client.create_stop_market_order(
                    symbol, reduce_side, filled_qty, stop_loss_price, reduce_only=True
                )
                
                if stop_order:
                    self.stop_orders[symbol] = {
                        'order_id': stop_order.get('orderId'),
                        'price': stop_loss_price,
                        'quantity': filled_qty
                    }
                
                # Take-profit seviyelerini hesapla ve emirleri oluştur
                if self.strategy.get('take_profit_targets'):
                    tp_levels = await self.risk_manager.calculate_take_profit_levels(
                        symbol, filled_price, signal_type
                    )
                    
                    if tp_levels:
                        self.take_profit_orders[symbol] = []
                        
                        for tp in tp_levels:
                            # Her TP seviyesi için miktar hesapla
                            tp_qty = filled_qty * (tp['percentage'] / 100)
                            
                            # TP emri oluştur
                            tp_order = await self.client.create_take_profit_market_order(
                                symbol, reduce_side, tp_qty, tp['price'], reduce_only=True
                            )
                            
                            if tp_order:
                                self.take_profit_orders[symbol].append({
                                    'level': tp['level'],
                                    'order_id': tp_order.get('orderId'),
                                    'price': tp['price'],
                                    'quantity': tp_qty,
                                    'target_pct': tp['target_pct']
                                })
                
                logger.info(f"{symbol} {signal_type} pozisyonu açıldı: {filled_qty} @ {filled_price}, "
                           f"SL: {stop_loss_price}, Kaldıraç: {leverage}x")
                
                # UI aktivite loguna ekle (eğer UI referansı varsa)
                if hasattr(self, 'ui') and self.ui:
                    self.ui.log_activity(
                        f"{symbol} {signal_type} pozisyonu açıldı: {filled_qty} @ {filled_price}",
                        "TRADE_OPEN",
                        {"symbol": symbol, "side": signal_type, "amount": filled_qty}
                    )
                
                return trade_info
            except Exception as e:
                logger.error(f"{symbol} pozisyonu açılırken hata: {e}\n{traceback.format_exc()}")
                return None
    
    async def close_position(self, symbol: str, reason: str = "Manuel kapatma"):
        """Açık pozisyonu kapatır."""
        async with self.position_lock:
            try:
                # Sembolde açık pozisyon var mı kontrol et
                position = self.risk_manager.get_position_for_symbol(symbol)
                if not position:
                    logger.info(f"{symbol} için açık pozisyon bulunamadı")
                    return None
                
                # Tüm açık stop ve take profit emirlerini iptal et
                await self.cancel_pending_orders(symbol)
                
                # Pozisyon yönünü belirle
                if position['side'] == "LONG":
                    close_side = "SELL"
                else:  # SHORT
                    close_side = "BUY"
                
                # Market emri ile pozisyonu kapat
                order_result = await self.client.create_market_order(
                    symbol, close_side, abs(position['amount']), reduce_only=True
                )
                
                if not order_result:
                    logger.error(f"{symbol} için pozisyon kapatma emri başarısız")
                    return None
                
                # Kapanış fiyatını al
                filled_price = float(order_result.get('avgPrice', position['mark_price']))
                filled_qty = float(order_result.get('executedQty', abs(position['amount'])))
                
                # PnL hesapla
                if position['side'] == "LONG":
                    pnl = (filled_price - position['entry_price']) * filled_qty
                else:  # SHORT
                    pnl = (position['entry_price'] - filled_price) * filled_qty
                
                # İşlemi kaydet
                trade_info = self.risk_manager.record_trade(
                    symbol, close_side, filled_qty, position['entry_price'],
                    exit_price=filled_price, pnl=pnl, trade_type="CLOSE"
                )
                
                # Active trades listesinden kaldır
                if symbol in self.active_trades:
                    del self.active_trades[symbol]
                
                # Stop orders listesinden kaldır
                if symbol in self.stop_orders:
                    del self.stop_orders[symbol]
                
                # Take profit orders listesinden kaldır
                if symbol in self.take_profit_orders:
                    del self.take_profit_orders[symbol]
                
                logger.info(f"{symbol} {position['side']} pozisyonu kapatıldı: {filled_qty} @ {filled_price}, "
                           f"PNL: {pnl:.2f} USDT, Neden: {reason}")
                
                # UI aktivite loguna ekle
                if hasattr(self, 'ui') and self.ui:
                    self.ui.log_activity(
                        f"{symbol} {position['side']} pozisyonu kapatıldı: {filled_qty} @ {filled_price}",
                        "TRADE_CLOSE",
                        {"symbol": symbol, "side": position['side'], "pnl": pnl}
                    )
                
                return trade_info
            except Exception as e:
                logger.error(f"{symbol} pozisyonu kapatılırken hata: {e}\n{traceback.format_exc()}")
                return None
    
    async def cancel_pending_orders(self, symbol: str):
        """Sembol için bekleyen tüm emirleri iptal eder."""
        try:
            # Tüm açık emirleri iptal et
            result = await self.client.cancel_all_open_orders(symbol)
            
            if result:
                logger.info(f"{symbol} için tüm bekleyen emirler iptal edildi")
            
            return result
        except Exception as e:
            logger.error(f"{symbol} için emirler iptal edilirken hata: {e}")
            return None
    
    async def update_trailing_stop(self, symbol: str, current_price: float):
        """Trailing stop seviyesini günceller."""
        try:
            # Sembolde açık pozisyon var mı kontrol et
            position = self.risk_manager.get_position_for_symbol(symbol)
            if not position:
                return None
            
            # Trailing stop aktif mi kontrol et
            if not self.strategy.get('trailing_sl'):
                return None
            
            # Mevcut stop emri var mı kontrol et
            if symbol not in self.stop_orders:
                return None
            
            current_stop = self.stop_orders[symbol]['price']
            
            # Pozisyon yönüne göre trailing stop mantığı
            if position['side'] == "LONG":
                # Long pozisyonda, fiyat yükseldikçe stop'u yukarı çek
                trailing_distance = current_price * (self.strategy.get('trailing_sl_distance') / 100)
                new_stop = current_price - trailing_distance
                
                # Yeni stop eskisinden yüksekse güncelle
                if new_stop > current_stop:
                    # Eşik değeri hesapla - %interval kadar hareket etmediyse güncelleme
                    threshold = current_stop * (1 + (self.strategy.get('trailing_sl_interval') / 100))
                    
                    if new_stop > threshold:
                        await self.update_stop_loss(symbol, new_stop)
            else:  # SHORT
                # Short pozisyonda, fiyat düştükçe stop'u aşağı çek
                trailing_distance = current_price * (self.strategy.get('trailing_sl_distance') / 100)
                new_stop = current_price + trailing_distance
                
                # Yeni stop eskisinden düşükse güncelle
                if new_stop < current_stop:
                    # Eşik değeri hesapla - %interval kadar hareket etmediyse güncelleme
                    threshold = current_stop * (1 - (self.strategy.get('trailing_sl_interval') / 100))
                    
                    if new_stop < threshold:
                        await self.update_stop_loss(symbol, new_stop)
            
            return self.stop_orders.get(symbol)
        except Exception as e:
            logger.error(f"{symbol} için trailing stop güncellenirken hata: {e}")
            return None
    
    async def update_stop_loss(self, symbol: str, new_stop_price: float):
        """Stop-loss seviyesini günceller."""
        try:
            # Sembolde açık pozisyon var mı kontrol et
            position = self.risk_manager.get_position_for_symbol(symbol)
            if not position:
                return None
            
            # Sembol hassasiyeti bilgilerini al
            symbol_info = await self.client.get_symbol_precision(symbol)
            price_precision = symbol_info['price_precision']
            
            # Fiyatı yuvarla
            new_stop_price = round(new_stop_price, price_precision)
            
            # Pozisyon yönünü belirle
            if position['side'] == "LONG":
                reduce_side = "SELL"
            else:  # SHORT
                reduce_side = "BUY"
            
            # Mevcut stop emrini iptal et
            if symbol in self.stop_orders:
                # Tüm açık emirleri iptal et
                await self.cancel_pending_orders(symbol)
            
            # Yeni stop emrini oluştur
            stop_order = await self.client.create_stop_market_order(
                symbol, reduce_side, abs(position['amount']), new_stop_price, reduce_only=True
            )
            
            if stop_order:
                self.stop_orders[symbol] = {
                    'order_id': stop_order.get('orderId'),
                    'price': new_stop_price,
                    'quantity': abs(position['amount'])
                }
                
                logger.info(f"{symbol} için stop-loss güncellendi: {new_stop_price}")
                
                # Active trade bilgisini güncelle
                if symbol in self.active_trades:
                    self.active_trades[symbol]['stop_loss'] = new_stop_price
                
                # UI aktivite loguna ekle
                if hasattr(self, 'ui') and self.ui:
                    self.ui.log_activity(
                        f"{symbol} için stop-loss güncellendi: {new_stop_price}",
                        "SL_UPDATE",
                        {"symbol": symbol, "stop_loss": new_stop_price}
                    )
                
                return self.stop_orders[symbol]
            
            return None
        except Exception as e:
            logger.error(f"{symbol} için stop-loss güncellenirken hata: {e}")
            return None
    
    async def process_partial_close(self, symbol: str, current_price: float):
        """Kısmen kar alma işlemini gerçekleştirir."""
        try:
            # Kısmi kapama aktif mi kontrol et
            if not self.strategy.get('partial_close_enabled'):
                return None
            
            # Sembolde açık pozisyon var mı kontrol et
            position = self.risk_manager.get_position_for_symbol(symbol)
            if not position:
                return None
            
            # Pozisyonun kar/zarar yüzdesini hesapla
            pnl_pct = self.risk_manager._calculate_position_pnl_percent(position, current_price)
            
            # Kısmi kapama eşiğini aştı mı kontrol et
            if pnl_pct > self.strategy.get('partial_close_threshold'):
                # Daha önce kısmen kapatılmış mı kontrol et (miktar kontrolü ile)
                if symbol in self.active_trades and self.active_trades[symbol].get('partially_closed'):
                    return None
                
                # Kapatılacak miktar yüzdesini al
                close_pct = self.strategy.get('partial_close_percentage')
                close_qty = abs(position['amount']) * (close_pct / 100)
                
                # Pozisyon yönünü belirle
                if position['side'] == "LONG":
                    close_side = "SELL"
                else:  # SHORT
                    close_side = "BUY"
                
                # Market emri ile pozisyonu kısmen kapat
                order_result = await self.client.create_market_order(
                    symbol, close_side, close_qty, reduce_only=True
                )
                
                if not order_result:
                    logger.error(f"{symbol} için kısmi kapama emri başarısız")
                    return None
                
                # Kapanış fiyatını al
                filled_price = float(order_result.get('avgPrice', current_price))
                filled_qty = float(order_result.get('executedQty', close_qty))
                
                # PnL hesapla
                if position['side'] == "LONG":
                    pnl = (filled_price - position['entry_price']) * filled_qty
                else:  # SHORT
                    pnl = (position['entry_price'] - filled_price) * filled_qty
                
                # İşlemi kaydet
                trade_info = self.risk_manager.record_trade(
                    symbol, close_side, filled_qty, position['entry_price'],
                    exit_price=filled_price, pnl=pnl, trade_type="TP"
                )
                
                # Active trade bilgisini güncelle
                if symbol in self.active_trades:
                    self.active_trades[symbol]['partially_closed'] = True
                    self.active_trades[symbol]['quantity'] -= filled_qty
                
                logger.info(f"{symbol} {position['side']} pozisyonu kısmen kapatıldı: "
                           f"{filled_qty} @ {filled_price}, PNL: {pnl:.2f} USDT")
                
                # UI aktivite loguna ekle
                if hasattr(self, 'ui') and self.ui:
                    self.ui.log_activity(
                        f"{symbol} {position['side']} pozisyonu kısmen kapatıldı: {filled_qty} @ {filled_price}",
                        "TP_HIT",
                        {"symbol": symbol, "pnl": pnl, "quantity": filled_qty}
                    )
                
                return trade_info
            
            return None
        except Exception as e:
            logger.error(f"{symbol} için kısmi kapama işlemi sırasında hata: {e}")
            return None
    
    async def check_and_process_signal(self, symbol: str, signal: Dict, market_volatility: float = 1.0):
        """Sinyal işleme ve pozisyon yönetimi."""
        try:
            # Sinyal işlem yapılabilir mi kontrol et
            if not signal['tradable']:
                return False
            
            # Mevcut pozisyonu kontrol et
            current_position = self.risk_manager.get_position_for_symbol(symbol)
            current_price = signal['last_price']
            
            # Mevcut pozisyon yoksa ve alım/satım sinyali varsa yeni pozisyon aç
            if not current_position:
                if signal['signal'] in ["LONG", "SHORT"]:
                    # Pozisyon açmayı dene
                    position = await self.open_position(symbol, signal['signal'], signal['signal_strength'], market_volatility)
                    
                    # Pozisyon açma başarısız olduysa bildir
                    if not position:
                        logger.warning(f"{symbol} için {signal['signal']} pozisyonu açılamadı")
                        
                        # UI aktivite loguna ekle (eğer UI referansı varsa)
                        if hasattr(self, 'ui') and self.ui:
                            self.ui.log_activity(
                                f"{symbol} için {signal['signal']} pozisyonu açılamadı",
                                "WARNING"
                            )
                        
                        return False
                    
                    # UI aktivite loguna ekle (eğer UI referansı varsa)
                    if hasattr(self, 'ui') and self.ui:
                        self.ui.log_activity(
                            f"{symbol} {signal['signal']} pozisyonu açıldı",
                            "TRADE_OPEN",
                            {"symbol": symbol, "side": signal['signal'], "strength": signal['signal_strength']}
                        )
                    
                    return True
                
                return False
            else:
                # Mevcut pozisyon varsa:
                # 1. Ters sinyal geldi mi kontrol et
                should_close, reason = self.risk_manager.should_close_position(symbol, current_price, signal['signal'])
                
                if should_close:
                    # Pozisyonu kapat
                    close_result = await self.close_position(symbol, reason)
                    
                    # Pozisyon kapatma başarısız olduysa bildir
                    if not close_result:
                        logger.warning(f"{symbol} pozisyonu kapatılamadı, neden: {reason}")
                        
                        # UI aktivite loguna ekle
                        if hasattr(self, 'ui') and self.ui:
                            self.ui.log_activity(
                                f"{symbol} pozisyonu kapatılamadı, neden: {reason}",
                                "WARNING"
                            )
                        
                        return False
                    
                    # Pozisyon kapatma başarılıysa ve sinyal hala aktifse yeni pozisyon aç
                    if signal['signal'] in ["LONG", "SHORT"]:
                        # İlk pozisyon başarıyla kapatıldı, şimdi yeni pozisyon aç
                        new_position = await self.open_position(symbol, signal['signal'], signal['signal_strength'], market_volatility)
                        
                        # Yeni pozisyon açma başarısız olduysa bildir
                        if not new_position:
                            logger.warning(f"{symbol} için ters yönde {signal['signal']} pozisyonu açılamadı")
                            
                            # UI aktivite loguna ekle
                            if hasattr(self, 'ui') and self.ui:
                                self.ui.log_activity(
                                    f"{symbol} için ters yönde {signal['signal']} pozisyonu açılamadı",
                                    "WARNING"
                                )
                            
                            return False
                        
                        # UI aktivite loguna ekle
                        if hasattr(self, 'ui') and self.ui:
                            self.ui.log_activity(
                                f"{symbol} ters yönde {signal['signal']} pozisyonu açıldı",
                                "TRADE_OPEN",
                                {"symbol": symbol, "side": signal['signal'], "strength": signal['signal_strength']}
                            )
                        
                        return True
                    
                    return True
                else:
                    # 2. Trailing stop güncelleme
                    trailing_updated = await self.update_trailing_stop(symbol, current_price)
                    
                    # 3. Kısmi kar alma
                    partial_close = await self.process_partial_close(symbol, current_price)
                    
                    return trailing_updated or partial_close
            
            return False
        except Exception as e:
            logger.error(f"{symbol} için sinyal işlenirken hata: {e}\n{traceback.format_exc()}")
            return False