"""
Risk management and position sizing module
"""

import logging
import math
from typing import Dict, List, Tuple, Optional
from datetime import datetime

from trading_bot.api.binance_client import BinanceClient
from trading_bot.core.strategy import StrategyParams

logger = logging.getLogger("trading_bot")
trade_logger = logging.getLogger("trade_log")

class RiskManager:
    """Risk yönetimi ve pozisyon boyutlandırma sınıfı."""
    
    def __init__(self, client: BinanceClient, strategy: StrategyParams):
        self.client = client
        self.strategy = strategy
        self.balances = {}
        self.open_positions = []
        self.position_history = []
        self.daily_pnl = {}
        self.drawdown = 0
        self.initial_balance = 0
        self.peak_balance = 0
        self.protection_mode = False
        self.protection_reason = ""
        self.protection_start_time = None
        self.position_history_timestamps = []  # Açılan pozisyonların zaman damgaları
        self.ui = None  # UI referansı
    
    async def initialize(self):
        """Risk yöneticisini başlatır."""
        logger.info("Risk yöneticisi başlatılıyor...")
        await self.update_account_info()
        
        # Başlangıç bakiyesini kaydet
        self.initial_balance = self.get_total_balance()
        self.peak_balance = self.initial_balance
        
        logger.info(f"Risk yöneticisi başlatıldı. Başlangıç bakiyesi: {self.initial_balance:.2f} USDT")
    
    async def update_account_info(self):
        """Hesap bilgilerini günceller ve manuel işlemleri tespit eder."""
        try:
            # Mevcut açık pozisyonları kaydet
            previous_positions = {pos['symbol']: pos for pos in self.open_positions}
            
            # Bakiye bilgisini al
            self.balances = await self.client.get_account_balance()
            
            # Açık pozisyonları al
            self.open_positions = await self.client.get_open_positions()
            
            # Manuel açılan yeni pozisyonları tespit et
            current_positions = {pos['symbol']: pos for pos in self.open_positions}
            
            # Yeni açılan pozisyonları bul
            for symbol, pos in current_positions.items():
                if symbol not in previous_positions:
                    # Yeni manuel pozisyon tespit edildi
                    self.record_trade(
                        symbol=symbol,
                        side="BUY" if pos['side'] == "LONG" else "SELL",
                        quantity=abs(pos['amount']),
                        entry_price=pos['entry_price'],
                        trade_type="MANUAL_OPEN"
                    )
                    
                    # UI aktivite loguna ekle (eğer UI referansı varsa)
                    if hasattr(self, 'ui') and self.ui:
                        self.ui.log_activity(
                            f"Manuel {pos['side']} pozisyonu tespit edildi: {symbol}",
                            "TRADE_OPEN",
                            {"symbol": symbol, "side": pos['side'], "amount": pos['amount']}
                        )
            
            # Kapatılan pozisyonları bul
            for symbol, prev_pos in previous_positions.items():
                if symbol not in current_positions:
                    # Manuel kapatılan pozisyon
                    self.record_trade(
                        symbol=symbol,
                        side="SELL" if prev_pos['side'] == "LONG" else "BUY",
                        quantity=abs(prev_pos['amount']),
                        entry_price=prev_pos['entry_price'],
                        exit_price=0,  # Exit fiyatını bilemeyiz
                        pnl=0,  # PnL hesabını tam yapamayız
                        trade_type="MANUAL_CLOSE"
                    )
                    
                    # UI aktivite loguna ekle
                    if hasattr(self, 'ui') and self.ui:
                        self.ui.log_activity(
                            f"Manuel {prev_pos['side']} pozisyonu kapatıldı: {symbol}",
                            "TRADE_CLOSE"
                        )
            
            # Toplam bakiyeyi hesapla
            total_balance = self.get_total_balance()
            
            # Peak balance'ı güncelle
            if total_balance > self.peak_balance:
                self.peak_balance = total_balance
            
            # Drawdown hesapla
            if self.peak_balance > 0:
                self.drawdown = ((self.peak_balance - total_balance) / self.peak_balance) * 100
            
            return True
        except Exception as e:
            logger.error(f"Hesap bilgileri güncellenirken hata: {e}")
            return False
    
    def get_total_balance(self) -> float:
        """Toplam hesap bakiyesini döndürür."""
        if 'USDT' in self.balances:
            # Wallet balance + unrealized PNL
            return self.balances['USDT']['wallet_balance'] + self.balances['USDT']['unrealized_pnl']
        return 0
    
    def get_available_balance(self) -> float:
        """Kullanılabilir bakiyeyi döndürür."""
        if 'USDT' in self.balances:
            return self.balances['USDT']['available_balance']
        return 0
    
    async def calculate_position_size(self, symbol: str, entry_price: float, 
                                    stop_loss_price: float, signal_type: str, 
                                    signal_strength: float) -> Tuple[float, int]:
        """Pozisyon boyutunu ve kaldıracı hesaplar."""
        try:
            # Koruma modu aktifse pozisyon açma
            if self.protection_mode:
                logger.warning(f"Koruma modu aktif, {symbol} için yeni pozisyon açılmayacak. Sebep: {self.protection_reason}")
                return 0, self.strategy.get('default_leverage')
            
            # Sembol hassasiyeti bilgilerini al
            symbol_info = await self.client.get_symbol_precision(symbol)
            
            # Kullanılabilir bakiye
            available_balance = self.get_available_balance()
            
            # Pozisyon boyutlandırma tipine göre işlem yap
            position_size_type = self.strategy.get('position_size_type')
            
            if position_size_type == 'FIXED':
                # Sabit pozisyon boyutu (USDT cinsinden)
                position_size_usdt = self.strategy.get('fixed_position_size')
            else:
                # Risk tabanlı pozisyon boyutu
                account_risk_pct = self.strategy.get('account_risk_per_trade')
                
                # Sinyal gücüne göre riski ayarla (daha güçlü sinyal = daha büyük pozisyon)
                adjusted_risk = account_risk_pct * (signal_strength / 100) * 1.5
                adjusted_risk = min(adjusted_risk, account_risk_pct)  # Risk sınırı
                
                # Riskin para karşılığını hesapla
                risk_amount = (available_balance * adjusted_risk) / 100
                
                # Stop loss mesafesini yüzde olarak hesapla
                if entry_price == 0 or stop_loss_price == 0:
                    sl_pct = self.strategy.get('static_sl_percent')
                else:
                    if signal_type == "LONG":
                        sl_pct = abs((entry_price - stop_loss_price) / entry_price) * 100
                    else:  # SHORT
                        sl_pct = abs((stop_loss_price - entry_price) / entry_price) * 100
                
                # Kaldıraç hesapla
                max_leverage = self.strategy.get('max_leverage')
                
                if self.strategy.get('auto_leverage'):
                    # ATR tabanlı otomatik kaldıraç hesaplama
                    # Düşük volatilite = yüksek kaldıraç, yüksek volatilite = düşük kaldıraç
                    target_leverage = int(max(1, min(max_leverage, 10 / sl_pct)))
                else:
                    target_leverage = self.strategy.get('default_leverage')
                
                # Kaldıraca göre pozisyon boyutu hesapla
                position_size_usdt = (risk_amount * target_leverage) / (sl_pct / 100)
                
                # Dinamik boyutlandırma tipinde ek kontroller
                if position_size_type == 'DYNAMIC':
                    # Piyasa koşullarına göre pozisyon boyutunu ayarla
                    market_condition_factor = 1.0
                    
                    # Açık pozisyon sayısına göre pozisyon boyutunu azalt
                    if len(self.open_positions) > 0:
                        # Her açık pozisyon için %20 azalt
                        reduction_factor = 1.0 - (len(self.open_positions) * 0.2)
                        reduction_factor = max(0.2, reduction_factor)  # En az %20 boyut
                        position_size_usdt *= reduction_factor
            
            # Minimum pozisyon kontrolü
            if position_size_usdt < symbol_info['min_notional']:
                logger.warning(f"{symbol} için hesaplanan pozisyon boyutu ({position_size_usdt:.2f} USDT) "
                              f"minimum değerin altında ({symbol_info['min_notional']} USDT)")
                return 0, target_leverage
            
            # Maksimum pozisyon kontrolü (hesabın %25'inden fazla olmasın)
            max_position_usdt = available_balance * 0.25
            position_size_usdt = min(position_size_usdt, max_position_usdt)
            
            # Coin miktarını hesapla
            quantity = position_size_usdt / entry_price
            
            # Kaldıraçlı miktarı hesapla
            leveraged_quantity = quantity * target_leverage
            
            # Lot büyüklüğüne göre yuvarla
            qty_step = symbol_info['min_qty']
            precision = symbol_info['qty_precision']
            
            rounded_quantity = math.floor(leveraged_quantity / qty_step) * qty_step
            rounded_quantity = round(rounded_quantity, precision)
            
            logger.info(f"{symbol} için pozisyon hesaplandı: {rounded_quantity} {symbol_info['base_asset']} "
                       f"({position_size_usdt:.2f} USDT), Kaldıraç: {target_leverage}x")
            
            return rounded_quantity, target_leverage
        except Exception as e:
            logger.error(f"{symbol} için pozisyon boyutu hesaplanırken hata: {e}")
            return 0, self.strategy.get('default_leverage')
    
    async def adaptive_position_sizing(self, symbol: str, signal_strength: float, risk_factors: Dict):
        """Piyasa koşullarına ve risk faktörlerine göre dinamik pozisyon boyutlandırma"""
        try:
            # Temel pozisyon boyutunu hesapla
            base_size = await self.calculate_standard_position_size(symbol)
            
            # Piyasa durumuna göre ayarla
            market_multiplier = 1.0
            if risk_factors.get('market_condition') == 'BEARISH':
                market_multiplier = 0.7
            elif risk_factors.get('market_condition') == 'BULLISH':
                market_multiplier = 1.2
            
            # Sinyal gücüne göre ayarla (min 0.5, max 1.5)
            signal_multiplier = 0.5 + (signal_strength / 100)
            
            # Volatilite göre ayarla
            volatility_multiplier = 1.0
            volatility = risk_factors.get('volatility', 1.0)
            if volatility > 2.0:
                volatility_multiplier = 0.8
            elif volatility < 0.7:
                volatility_multiplier = 1.2
            
            # Son fiyat hareketine göre ayarla
            recent_move = risk_factors.get('recent_price_change', 0)
            price_action_multiplier = 1.0
            if abs(recent_move) > 5.0:  # Son 24 saatte %5'ten fazla hareket
                price_action_multiplier = 0.7
            
            # Toplam açık pozisyon sayısına göre ayarla
            positions_multiplier = 1.0
            open_positions_count = len(self.open_positions)
            max_positions = self.strategy.get('max_open_positions')
            if open_positions_count > max_positions * 0.7:  # 70%'ten fazla doluluk
                positions_multiplier = 0.8
            
            # Drawdown durumuna göre ayarla
            drawdown_multiplier = 1.0
            if self.drawdown > 5.0:  # %5'ten fazla drawdown
                drawdown_multiplier = 0.6
            
            # Tüm faktörleri birleştir
            final_size = base_size * market_multiplier * signal_multiplier * volatility_multiplier * price_action_multiplier * positions_multiplier * drawdown_multiplier
            
            logger.info(f"{symbol} için adaptif pozisyon boyutu hesaplandı: {final_size:.4f} (Baz: {base_size:.4f}, "
                      f"Piyasa: x{market_multiplier:.2f}, Sinyal: x{signal_multiplier:.2f}, "
                      f"Volatilite: x{volatility_multiplier:.2f}, Fiyat Hareketi: x{price_action_multiplier:.2f})")
            
            return final_size
        except Exception as e:
            logger.error(f"{symbol} için adaptif pozisyon boyutu hesaplanırken hata: {e}")
            return 0
    
    async def calculate_standard_position_size(self, symbol: str) -> float:
        """Temel pozisyon boyutunu hesaplar, adaptif boyutlandırma için kullanılır"""
        try:
            # Hesap riskini al
            account_risk_pct = self.strategy.get('account_risk_per_trade')
            available_balance = self.get_available_balance()
            
            # Riskin para karşılığını hesapla
            risk_amount = (available_balance * account_risk_pct) / 100
            
            # Son fiyatı al
            last_price = await self.client.get_mark_price(symbol)
            
            # Varsayılan stop loss oranını kullan
            sl_pct = self.strategy.get('static_sl_percent')
            
            # Varsayılan kaldıracı al
            leverage = self.strategy.get('default_leverage')
            
            # Pozisyon boyutu hesapla
            position_size_usdt = (risk_amount * leverage) / (sl_pct / 100)
            
            # Maksimum pozisyon kontrolü (hesabın %25'inden fazla olmasın)
            max_position_usdt = available_balance * 0.25
            position_size_usdt = min(position_size_usdt, max_position_usdt)
            
            return position_size_usdt
        except Exception as e:
            logger.error(f"{symbol} için standart pozisyon boyutu hesaplanırken hata: {e}")
            return 0
    
    def detect_market_anomalies(self, market_data: Dict) -> bool:
        """Piyasada anormal durumları tespit eder ve koruyucu önlemler alır"""
        try:
            # BTC volatilitesi aniden arttı mı?
            btc_volatility = market_data.get('btc_volatility', 1.0)
            
            # Volatilite eşiği aşıldı mı?
            if btc_volatility > 3.0:  # Aşırı volatilite
                self.enter_protection_mode(f"Yüksek BTC volatilitesi: {btc_volatility:.2f}")
                return True
            
            # Toplam açık pozisyon sayısı hızla arttı mı?
            position_change_rate = self._calculate_position_change_rate()
            if position_change_rate > 300:  # %300'den fazla artış
                self.enter_protection_mode(f"Hızlı pozisyon artışı: %{position_change_rate:.1f}")
                return True
            
            # Hızlı drawdown oluştu mu?
            if self.drawdown > 5.0 and self._is_rapid_drawdown():
                self.enter_protection_mode(f"Hızlı drawdown: %{self.drawdown:.2f}")
                return True
            
            # Aşırı fiyat hareketi var mı?
            if market_data.get('extreme_price_movement', False):
                self.enter_protection_mode("Aşırı fiyat hareketi tespit edildi")
                return True
            
            # Normal piyasa, koruma modunu devre dışı bırak
            if self.protection_mode and self._should_exit_protection_mode():
                self.exit_protection_mode()
            
            return False
        except Exception as e:
            logger.error(f"Piyasa anomalileri tespit edilirken hata: {e}")
            return False
    
    def _calculate_position_change_rate(self) -> float:
        """Açık pozisyon sayısındaki değişim oranını hesaplar"""
        try:
            now = datetime.now()
            one_hour_ago = now.timestamp() - 3600  # 1 saat önce
            
            # Son 1 saatte açılan pozisyon sayısı
            recent_positions = sum(1 for ts in self.position_history_timestamps if ts > one_hour_ago)
            
            # Normal saatlik ortalama (son 24 saate göre)
            one_day_ago = now.timestamp() - 86400  # 24 saat önce
            day_positions = sum(1 for ts in self.position_history_timestamps if ts > one_day_ago)
            hourly_avg = day_positions / 24 if day_positions > 0 else 1
            
            # Değişim oranı
            if hourly_avg > 0:
                change_rate = (recent_positions / hourly_avg - 1) * 100
                return max(0, change_rate)
            
            return 0
        except Exception as e:
            logger.error(f"Pozisyon değişim oranı hesaplanırken hata: {e}")
            return 0
    
    def _is_rapid_drawdown(self) -> bool:
        """Drawdown'ın hızlı olup olmadığını kontrol eder"""
        # Burada daha karmaşık bir mantık uygulanabilir
        # Şimdilik sadece %5'in üzerindeki drawdown'ı hızlı kabul ediyoruz
        return self.drawdown > 5.0
    
    def enter_protection_mode(self, reason: str):
        """Koruma modunu aktive eder"""
        if not self.protection_mode:
            logger.warning(f"Koruma modu aktive edildi: {reason}")
            
            # Tüm yeni giriş işlemlerini durdur
            self.protection_mode = True
            self.protection_reason = reason
            self.protection_start_time = datetime.now()
            
            # Açık pozisyonlara trailing stop ekle veya mevcut stopları sıkılaştır
            self._tighten_all_stop_losses()
    
    def exit_protection_mode(self):
        """Koruma modundan çıkar"""
        if self.protection_mode:
            duration = datetime.now() - self.protection_start_time
            hours = duration.total_seconds() / 3600
            
            logger.info(f"Koruma modu deaktive edildi. Süre: {hours:.1f} saat. Sebep: {self.protection_reason}")
            
            self.protection_mode = False
            self.protection_reason = ""
            self.protection_start_time = None
    
    def _should_exit_protection_mode(self) -> bool:
        """Koruma modundan çıkılması gerekip gerekmediğini kontrol eder"""
        if not self.protection_mode or not self.protection_start_time:
            return False
        
        # 2 saatten uzun süre koruma modunda kaldıysak çık
        duration = datetime.now() - self.protection_start_time
        if duration.total_seconds() > 7200:  # 2 saat = 7200 saniye
            return True
        
        # Piyasa normale döndü mü kontrol et (burada daha fazla piyasa kontrolü yapılabilir)
        return self.drawdown < 3.0  # Drawdown %3'ün altına indiyse
    
    def _tighten_all_stop_losses(self):
        """Tüm açık pozisyonların stop loss seviyelerini sıkılaştırır"""
        # Bu metod position_manager ile entegre çalışacak şekilde implement edilmeli
        logger.info("Tüm açık pozisyonlar için stop loss seviyeleri sıkılaştırılıyor")
        
        # Gerçek implementasyon position_manager.update_stop_loss metodunu çağırmalı
        # Bu şu anda bir taslak metottur
        pass
    
    async def calculate_take_profit_levels(self, symbol: str, entry_price: float, 
                                         signal_type: str) -> List[Dict]:
        """Take profit seviyelerini hesaplar."""
        try:
            # Take profit hedefleri ve miktarları
            tp_targets = self.strategy.get('take_profit_targets')
            tp_quantities = self.strategy.get('take_profit_quantities')
            
            # Hedefler yoksa boş liste döndür
            if not tp_targets or not tp_quantities:
                return []
            
            # Sembol hassasiyeti bilgilerini al
            symbol_info = await self.client.get_symbol_precision(symbol)
            price_precision = symbol_info['price_precision']
            
            # Take profit seviyeleri
            tp_levels = []
            
            for i, (target_pct, qty_pct) in enumerate(zip(tp_targets, tp_quantities)):
                # Fiyatı hesapla
                if signal_type == "LONG":
                    tp_price = entry_price * (1 + (target_pct / 100))
                else:  # SHORT
                    tp_price = entry_price * (1 - (target_pct / 100))
                
                # Fiyatı yuvarla
                tp_price = round(tp_price, price_precision)
                
                tp_levels.append({
                    'level': i + 1,
                    'price': tp_price,
                    'percentage': qty_pct,
                    'target_pct': target_pct
                })
            
            return tp_levels
        except Exception as e:
            logger.error(f"{symbol} için take profit seviyeleri hesaplanırken hata: {e}")
            return []
    
    async def calculate_stop_loss(self, symbol: str, entry_price: float, signal_type: str, 
                                market_volatility: float) -> float:
        """Stop loss seviyesini hesaplar."""
        try:
            # Sembol hassasiyeti bilgilerini al
            symbol_info = await self.client.get_symbol_precision(symbol)
            price_precision = symbol_info['price_precision']
            
            # Statik stop loss yüzdesi
            static_sl_pct = self.strategy.get('static_sl_percent')
            
            # Piyasa volatilitesine göre ayarla
            adjusted_sl_pct = static_sl_pct * market_volatility
            
            # Makul bir aralıkta tut
            adjusted_sl_pct = max(0.5, min(10.0, adjusted_sl_pct))
            
            # Stop loss fiyatını hesapla
            if signal_type == "LONG":
                sl_price = entry_price * (1 - (adjusted_sl_pct / 100))
            else:  # SHORT
                sl_price = entry_price * (1 + (adjusted_sl_pct / 100))
            
            # Fiyatı yuvarla
            sl_price = round(sl_price, price_precision)
            
            logger.info(f"{symbol} için stop loss hesaplandı: {sl_price} ({adjusted_sl_pct:.2f}%)")
            
            return sl_price
        except Exception as e:
            logger.error(f"{symbol} için stop loss hesaplanırken hata: {e}")
            
            # Hata durumunda varsayılan SL yüzdesini kullan
            sl_pct = self.strategy.get('static_sl_percent')
            
            if signal_type == "LONG":
                return entry_price * (1 - (sl_pct / 100))
            else:  # SHORT
                return entry_price * (1 + (sl_pct / 100))
    
    async def check_risk_limits(self) -> bool:
        """Risk limitlerini kontrol eder."""
        try:
            # Koruma modu aktifse risk limitini aştık demektir
            if self.protection_mode:
                logger.warning(f"Koruma modu aktif, risk limitlerini aştık. Sebep: {self.protection_reason}")
                return False
            
            # Drawdown limiti kontrol et
            max_drawdown = self.strategy.get('max_drawdown')
            if self.drawdown > max_drawdown:
                logger.warning(f"Maksimum drawdown aşıldı: {self.drawdown:.2f}% > {max_drawdown}%")
                return False
            
            # Açık pozisyon sayısı limitini kontrol et
            max_positions = self.strategy.get('max_open_positions')
            if len(self.open_positions) >= max_positions:
                logger.info(f"Maksimum açık pozisyon sayısına ulaşıldı: {len(self.open_positions)}/{max_positions}")
                return False
            
            # Günlük işlem limitini kontrol et
            today = datetime.now().strftime('%Y-%m-%d')
            daily_trade_count = self.daily_pnl.get(today, {}).get('trade_count', 0)
            max_daily_trades = self.strategy.get('max_daily_trades')
            
            if daily_trade_count >= max_daily_trades:
                logger.info(f"Günlük maksimum işlem sayısına ulaşıldı: {daily_trade_count}/{max_daily_trades}")
                return False
            
            # Günlük kar/zarar limiti kontrolü
            daily_profit = self.daily_pnl.get(today, {}).get('total_pnl', 0)
            daily_profit_pct = (daily_profit / self.initial_balance) * 100 if self.initial_balance > 0 else 0
            
            # Kar hedefine ulaşıldı mı?
            profit_threshold = self.strategy.get('profit_threshold_daily')
            if daily_profit_pct > profit_threshold:
                logger.info(f"Günlük kar hedefine ulaşıldı: {daily_profit_pct:.2f}% > {profit_threshold}%")
                return False
            
            # Zarar limitini aştı mı?
            loss_threshold = self.strategy.get('loss_threshold_daily')
            if daily_profit_pct < -loss_threshold:
                logger.warning(f"Günlük zarar limiti aşıldı: {daily_profit_pct:.2f}% < -{loss_threshold}%")
                return False
            
            # Toplam hesap riski kontrolü
            account_risk = self._calculate_total_account_risk()
            max_account_risk = self.strategy.get('max_account_risk')
            
            if account_risk > max_account_risk:
                logger.warning(f"Maksimum hesap riski aşıldı: {account_risk:.2f}% > {max_account_risk}%")
                return False
            
            return True
        except Exception as e:
            logger.error(f"Risk limitleri kontrol edilirken hata: {e}")
            return False
    
    def _calculate_total_account_risk(self) -> float:
        """Toplam hesap riskini hesaplar."""
        total_risk = 0
        total_balance = self.get_total_balance()
        
        if total_balance <= 0:
            return 0
        
        # Her açık pozisyon için riski hesapla
        for pos in self.open_positions:
            # Pozisyon değeri
            position_value = abs(pos['amount'] * pos['mark_price'])
            
            # Pozisyon risk yüzdesi (leverage dikkate alınarak)
            position_risk_pct = (position_value / (total_balance * pos['leverage'])) * 100
            
            total_risk += position_risk_pct
        
        return total_risk
    
    def record_trade(self, symbol: str, side: str, quantity: float, 
                   entry_price: float, exit_price: float = None, 
                   pnl: float = None, trade_type: str = "OPEN"):
        """Ticareti kaydeder ve istatistikleri günceller."""
        try:
            now = datetime.now()
            today = now.strftime('%Y-%m-%d')
            
            trade_info = {
                'symbol': symbol,
                'side': side,
                'quantity': quantity,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'pnl': pnl,
                'type': trade_type,
                'timestamp': now
            }
            
            # Pozisyon geçmişine ekle
            self.position_history.append(trade_info)
            
            # Açılış işlemi ise zaman damgasını ekle
            if trade_type == "OPEN":
                self.position_history_timestamps.append(now.timestamp())
            
            # Günlük PnL istatistiklerini güncelle
            if today not in self.daily_pnl:
                self.daily_pnl[today] = {
                    'total_pnl': 0,
                    'trade_count': 0,
                    'win_count': 0,
                    'loss_count': 0
                }
            
            # Ticaret sayısını artır
            self.daily_pnl[today]['trade_count'] += 1
            
            # Kapatma işlemi ise PnL güncelle
            if trade_type in ["CLOSE", "SL", "TP"] and pnl is not None:
                self.daily_pnl[today]['total_pnl'] += pnl
                
                if pnl > 0:
                    self.daily_pnl[today]['win_count'] += 1
                else:
                    self.daily_pnl[today]['loss_count'] += 1
            
            # Ticaret loguna kaydet
            trade_logger.info(f"{trade_type} {symbol} {side} {quantity} @ {entry_price}"
                             f"{f' -> {exit_price} (PNL: {pnl:.2f})' if exit_price else ''}")
            
            return trade_info
        except Exception as e:
            logger.error(f"Ticaret kaydedilirken hata: {e}")
            return None
    
    def get_daily_stats(self) -> Dict:
        """Günlük ticaret istatistiklerini döndürür."""
        today = datetime.now().strftime('%Y-%m-%d')
        
        if today in self.daily_pnl:
            stats = self.daily_pnl[today]
            win_rate = (stats['win_count'] / stats['trade_count'] * 100) if stats['trade_count'] > 0 else 0
            
            return {
                'date': today,
                'total_pnl': stats['total_pnl'],
                'pnl_percentage': (stats['total_pnl'] / self.initial_balance * 100) if self.initial_balance > 0 else 0,
                'trade_count': stats['trade_count'],
                'win_count': stats['win_count'],
                'loss_count': stats['loss_count'],
                'win_rate': win_rate
            }
        
        return {
            'date': today,
            'total_pnl': 0,
            'pnl_percentage': 0,
            'trade_count': 0,
            'win_count': 0,
            'loss_count': 0,
            'win_rate': 0
        }
    
    def get_position_for_symbol(self, symbol: str) -> Optional[Dict]:
        """Belirli bir sembol için açık pozisyonu döndürür."""
        for pos in self.open_positions:
            if pos['symbol'] == symbol:
                return pos
        return None
    
    def should_close_position(self, symbol: str, current_price: float, signal_type: str) -> Tuple[bool, str]:
        """Pozisyonun kapatılması gerekip gerekmediğini kontrol eder."""
        position = self.get_position_for_symbol(symbol)
        
        if not position:
            return False, ""
        
        # Pozisyon yönü
        position_side = position['side']
        
        # Ters sinyal geldi mi?
        if (position_side == "LONG" and signal_type == "SHORT") or (position_side == "SHORT" and signal_type == "LONG"):
            return True, "Ters sinyal"
        
        # Kısmen kar alma kontrolü
        if self.strategy.get('partial_close_enabled'):
            pnl_pct = self._calculate_position_pnl_percent(position, current_price)
            
            if pnl_pct > self.strategy.get('partial_close_threshold'):
                return True, "Kısmi kar alma"
        
        return False, ""
    
    def _calculate_position_pnl_percent(self, position: Dict, current_price: float) -> float:
        """Pozisyonun kar/zarar yüzdesini hesaplar."""
        if position['side'] == "LONG":
            pnl_pct = ((current_price - position['entry_price']) / position['entry_price']) * 100
        else:  # SHORT
            pnl_pct = ((position['entry_price'] - current_price) / position['entry_price']) * 100
        
        return pnl_pct