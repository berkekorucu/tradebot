"""
Enhanced Console UI for trading bot with comprehensive information display
"""

import logging
import time
import psutil
import asyncio
import os
import sys
from typing import Dict, List, Optional, Any
from datetime import datetime

from rich.table import Table
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich.align import Align
from rich import box
from rich.console import Group

logger = logging.getLogger("trading_bot")

class BotUI:
    """Trading Bot için gelişmiş konsol UI sınıfı."""
    
    def __init__(self, testnet=False, version="1.0.0"):
        # Rich konsol ayarları - Windows uyumluluğu için
        os.environ["TERM"] = "xterm-256color"
        self.console = Console(color_system="auto", highlight=False)
        
        self.layout = None
        self.live = None
        self.testnet = testnet
        self.version = version
        self.running = False
        self.start_time = datetime.now()
        
        # Performance tracking
        self.daily_stats_history = {}
        self.weekly_stats = {
            'total_pnl': 0,
            'win_count': 0,
            'loss_count': 0,
            'trade_count': 0
        }
        
        # Activity log
        self.activity_log = []
        
        # Target cryptocurrencies being watched
        self.target_cryptos = {}
        
        # Sembol fiyat önbelleği ve son güncelleme zamanları
        self.symbol_price_cache = {}
        self.price_update_times = {}
        
        # Sinyal depolama
        self.active_signals = []
        self.last_signal_update = 0
        
        # System stats
        self.system_stats = {
            'api_connected': True,
            'market_data_flow': 'Normal',
            'risk_limits_ok': True,
            'memory_usage': 0,
            'cpu_usage': 0
        }
        
        # Processing stats
        self.processing_stats = {
            'processed_symbols': 0,
            'total_symbols': 0,
            'signals_generated': 0,
            'max_positions': 5,
            'avg_signal_strength': 0,
            'most_active_symbol': '',
            'most_active_count': 0
        }
        
        # Bileşen referansları
        self.risk_manager = None
        self.market_data = None
        self.position_manager = None
        
        # Son fiyat güncelleme kontrolü
        self.last_price_update_check = 0
        self.force_price_update = False
        
        logger.info("BotUI başlatıldı")
    
    def setup(self, symbols_count=0):
        """UI bileşenlerini hazırlar."""
        try:
            logger.info("UI bileşenleri hazırlanıyor...")
            self.layout = Layout()
            
            # Main layout structure (removed footer)
            self.layout.split(
                Layout(name="header", size=3),
                Layout(name="body")
            )
            
            # Body layout structure
            self.layout["body"].split_row(
                Layout(name="left_column", ratio=1),
                Layout(name="right_column", ratio=1)
            )
            
            # Left column (top and bottom)
            self.layout["left_column"].split(
                Layout(name="top_left", ratio=1),
                Layout(name="positions", ratio=1),
                Layout(name="activity", ratio=1)
            )
            
            # Right column (top and bottom)
            self.layout["right_column"].split(
                Layout(name="target_cryptos", ratio=1),
                Layout(name="signals", ratio=1),
                Layout(name="system", ratio=1)
            )
            
            # Top left panel split into market status and performance
            self.layout["top_left"].split_row(
                Layout(name="market_status"),
                Layout(name="performance")
            )
            
            # System panel split into bot status and statistics
            self.layout["system"].split_row(
                Layout(name="bot_status"),
                Layout(name="statistics")
            )
            
            # Initial content setup
            self._update_header()
            self._update_market_status({})
            self._update_performance({})
            self._update_target_cryptos([])
            self._update_positions([])
            self._update_signals([])
            self._update_activity_log()
            self._update_bot_status()
            self._update_statistics()
            
            # Set total symbols count
            self.processing_stats['total_symbols'] = symbols_count
            
            # Live display
            self.live = Live(self.layout, refresh_per_second=2, screen=True)
            self.running = True
            
            logger.info("UI bileşenleri başarıyla hazırlandı")
            return True
        except Exception as e:
            logger.error(f"UI ayarlanırken hata: {e}")
            # Basit terminal çıktısı olarak bilgi ver
            print(f"UI ayarlanırken hata: {e}")
            print("Basit terminal modunda devam ediliyor...")
            self.running = False
            return False
    
    def start(self):
        """Live UI'ı başlatır."""
        try:
            if self.live:
                logger.info("Live UI başlatılıyor...")
                self.live.start()
                logger.info("Live UI başarıyla başlatıldı")
            else:
                logger.error("Live nesnesi başlatılmamış, UI başlatılamadı")
                print("UI başlatılamadı. Lütfen programı yeniden başlatın.")
        except Exception as e:
            logger.error(f"UI başlatılırken hata: {e}")
            print(f"UI başlatılırken hata oluştu: {e}")
            # Basit terminal moduna geç
            self.running = False
    
    def stop(self):
        """Live UI'ı durdurur."""
        try:
            if self.live:
                logger.info("UI durduruluyor...")
                self.live.stop()
                logger.info("UI başarıyla durduruldu")
            self.running = False
        except Exception as e:
            logger.error(f"UI durdurulurken hata: {e}")
    
    def log_activity(self, message: str, activity_type: str = "INFO", data: Dict = None):
        """Add an activity to the activity log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Define emoji for different activity types
        emoji_map = {
            "TRADE_OPEN": "➤",
            "TRADE_CLOSE": "✓",
            "SIGNAL": "★",
            "WARNING": "⚠",
            "ERROR": "✗",
            "SL_UPDATE": "⚠",
            "TP_HIT": "💰",
            "OPPORTUNITY": "🎯",  # Yeni aktivite tipi: Fırsat tespiti
            "COOLING": "❄️",      # Yeni aktivite tipi: Soğuma süreci
            "INFO": "ℹ"
        }
        
        emoji = emoji_map.get(activity_type, "•")
        
        # Log to file as well
        logger.info(f"[{activity_type}] {message}")
        
        # Add to activity log
        self.activity_log.append({
            "timestamp": timestamp,
            "message": message,
            "type": activity_type,
            "emoji": emoji,
            "data": data or {}
        })
        
        # Keep only last 50 activities
        if len(self.activity_log) > 50:
            self.activity_log = self.activity_log[-50:]
    
    def update_system_stats(self):
        """Update system statistics."""
        try:
            self.system_stats['memory_usage'] = psutil.Process().memory_info().rss / (1024 * 1024)  # MB
            self.system_stats['cpu_usage'] = psutil.cpu_percent()
        except Exception as e:
            logger.debug(f"Sistem istatistikleri güncellenirken hata: {e}")
            # Ignore if psutil is not available or fails
    
    def track_symbol_activity(self, symbol: str, has_signal: bool = False):
        """Track symbol activity for statistics."""
        if symbol not in self.target_cryptos:
            self.target_cryptos[symbol] = {
                'signals_count': 0,
                'last_price': 0,
                'trend': 'NEUTRAL',
                'volatility': 2,  # 1-5 scale
                'signal_strength': 0,
                'opportunity_score': 0  # Fırsat puanı eklendi
            }
        
        if has_signal:
            self.target_cryptos[symbol]['signals_count'] += 1
            
            # Update most active symbol
            if self.target_cryptos[symbol]['signals_count'] > self.processing_stats['most_active_count']:
                self.processing_stats['most_active_symbol'] = symbol
                self.processing_stats['most_active_count'] = self.target_cryptos[symbol]['signals_count']
    
    def update(self, positions: List[Dict], signals: List[Dict], daily_stats: Dict, 
              market_state: Optional[Dict] = None, running: bool = True,
              watched_symbols: Optional[List[Dict]] = None):
        """UI'ı güncelleyen metot."""
        if not self.live or not self.layout or not self.running:
            # UI çalışmıyorsa veya hazır değilse, basit terminal çıktısı ver
            self._fallback_terminal_update(positions, signals, daily_stats)
            return
        
        try:
            # Update running state
            self.running = running
            
            # Update system stats
            self.update_system_stats()
            
            # Aktif sinyalleri sakla
            if signals:
                tradable_signals = [s for s in signals if s.get('tradable', False)]
                if tradable_signals:
                    self.active_signals = tradable_signals
                    self.last_signal_update = time.time()
            
            # Fiyat güncellemelerini kontrol et - her 5 saniyede bir 
            # veya UI güncelleme sıklığına göre periyodik olarak
            current_time = time.time()
            if current_time - self.last_price_update_check >= 5 or self.force_price_update:
                # Aktif sinyaller ve açık pozisyonlar için fiyatları güncelle
                self._update_prices_for_active_items(positions)
                self.last_price_update_check = current_time
                self.force_price_update = False
            
            # Update processing stats
            self.processing_stats['processed_symbols'] = len(watched_symbols) if watched_symbols else 0
            self.processing_stats['signals_generated'] = len(signals)
            
            # Calculate average signal strength
            if signals:
                self.processing_stats['avg_signal_strength'] = sum(s.get('signal_strength', 0) for s in signals) / len(signals)
            
            # Track weekly stats
            today = datetime.now().strftime('%Y-%m-%d')
            if today not in self.daily_stats_history:
                self.daily_stats_history[today] = daily_stats
                
                # Update weekly stats
                self.weekly_stats['total_pnl'] += daily_stats.get('total_pnl', 0)
                self.weekly_stats['win_count'] += daily_stats.get('win_count', 0)
                self.weekly_stats['loss_count'] += daily_stats.get('loss_count', 0)
                self.weekly_stats['trade_count'] += daily_stats.get('trade_count', 0)
            
            # Track target cryptocurrencies
            for signal in signals:
                symbol = signal.get('symbol', '')
                if symbol:
                    self.track_symbol_activity(symbol, True)
                    self.target_cryptos[symbol]['last_price'] = signal.get('last_price', 0)
                    self.target_cryptos[symbol]['trend'] = signal.get('signal', 'NEUTRAL')
                    self.target_cryptos[symbol]['signal_strength'] = signal.get('signal_strength', 0)
                    
                    # Eğer sinyal içinde opportunity_score varsa, bunu kullan
                    if 'opportunity_score' in signal:
                        self.target_cryptos[symbol]['opportunity_score'] = signal.get('opportunity_score', 0)
                    
                    # Sembol fiyat önbelleği güncellemesi
                    self.symbol_price_cache[symbol] = signal.get('last_price', 0)
                    self.price_update_times[symbol] = time.time()
            
            # For watched symbols not in signals
            if watched_symbols:
                for symbol_data in watched_symbols:
                    symbol = symbol_data.get('symbol', '')
                    if symbol and symbol not in self.target_cryptos:
                        self.track_symbol_activity(symbol)
                        if 'last_price' in symbol_data:
                            self.target_cryptos[symbol]['last_price'] = symbol_data['last_price']
                            
                            # Sembol fiyat önbelleği güncellemesi
                            self.symbol_price_cache[symbol] = symbol_data['last_price']
                            self.price_update_times[symbol] = time.time()
                            
                        # Eğer market_data referansı varsa, fırsat puanını al
                        if hasattr(self, 'market_data') and self.market_data:
                            if hasattr(self.market_data, 'target_pool'):
                                target_data = self.market_data.target_pool.get_target_data(symbol)
                                if target_data and 'score' in target_data:
                                    self.target_cryptos[symbol]['opportunity_score'] = target_data['score']
            
            # Update UI components
            self._update_header(daily_stats)
            if market_state:
                self._update_market_status(market_state)
            self._update_performance(daily_stats)
            
            # Hedef kripto paraları fırsat puanına göre sırala
            top_symbols = sorted(
                [(symbol, data) for symbol, data in self.target_cryptos.items()],
                key=lambda x: x[1]['opportunity_score'],  # Fırsat puanına göre sırala
                reverse=True
            )[:10]  # Show top 10
            
            self._update_target_cryptos(top_symbols)
            self._update_positions(positions)
            
            # Sinyalleri güncelle - eğer aktif sinyaller varsa onları kullan
            # aksi takdirde gelen sinyalleri kullan
            signals_to_show = signals
            if not signals and self.active_signals:
                # Aktif sinyaller varsa ve şu anki güncelleme ile gelen sinyaller yoksa
                # saklanan sinyalleri göster
                signals_to_show = self.active_signals
            
            self._update_signals(signals_to_show)
            self._update_activity_log()
            self._update_bot_status()
            self._update_statistics()
            
        except Exception as e:
            # UI güncellenirken hata olsa bile çökmeyi engelle
            logger.error(f"UI güncellenirken hata: {e}")
            # UI hatası için yedek terminal çıktısına geç
            self._fallback_terminal_update(positions, signals, daily_stats)
            
            # Eğer ciddi bir hata varsa UI'yi yeniden başlatmayı dene
            self._try_restart_ui()
    
    def _fallback_terminal_update(self, positions, signals, daily_stats):
        """UI çalışmadığında terminal çıktısı sağlar"""
        try:
            # Terminal için basit durum çıktısı
            print("\033[2J\033[H")  # Ekranı temizle
            print(f"Binance Futures Trading Bot | v{self.version} {'[TEST MODE]' if self.testnet else ''}")
            print("-" * 80)
            
            # Durum bilgisi
            print(f"Durum: {'ÇALIŞIYOR' if self.running else 'DURAKLATILDI'}")
            
            # Açık pozisyonlar
            print(f"\nAçık Pozisyonlar: {len(positions)}/{self.processing_stats['max_positions']}")
            for pos in positions:
                symbol = pos['symbol']
                side = pos['side']
                amount = abs(pos['amount'])
                entry_price = pos['entry_price']
                mark_price = pos['mark_price']
                pnl = pos['pnl']
                leverage = pos.get('leverage', 1)
                margin = (amount * entry_price) / leverage
                print(f"  {symbol}: {side} {amount:.6f} @ {entry_price:.6f} | Margin: {margin:.2f} USDT | Kaldıraç: {leverage}x | PNL: {pnl:.2f} USDT")
            
            # İşlenebilir sinyaller
            tradable_signals = [s for s in signals if s.get('tradable', False)]
            print(f"\nİşlem Bekleyen Sinyaller: {len(tradable_signals)}")
            for signal in tradable_signals[:3]:  # En güçlü 3 sinyal
                symbol = signal['symbol']
                signal_type = signal['signal']
                strength = signal['signal_strength']
                print(f"  {symbol}: {signal_type} {strength:.0f}%")
            
            # Günlük istatistikler
            pnl = daily_stats.get('total_pnl', 0)
            win_count = daily_stats.get('win_count', 0)
            loss_count = daily_stats.get('loss_count', 0)
            trade_count = daily_stats.get('trade_count', 0)
            win_rate = (win_count / trade_count * 100) if trade_count > 0 else 0
            
            print(f"\nGünlük Performans: PNL={pnl:.2f} USDT | İşlemler={trade_count} | Başarı Oranı={win_rate:.1f}%")
            
            # Son işlemler
            print("\nSon Aktiviteler:")
            for activity in self.activity_log[-3:]:
                timestamp = activity.get("timestamp", "")
                message = activity.get("message", "")
                print(f"  {timestamp} - {message}")
            
            print("-" * 80)
            print(f"İşlenen Sembol: {self.processing_stats['processed_symbols']}/{self.processing_stats['total_symbols']} | "
                 f"Ortalama Sinyal Gücü: {self.processing_stats['avg_signal_strength']:.1f}%")
            
        except Exception as e:
            # Basit terminal çıktısı da başarısız olursa
            logger.error(f"Basit terminal çıktısı oluşturulurken hata: {e}")
    
    def _try_restart_ui(self):
        """UI'yi sorun olduğunda yeniden başlatmayı dener"""
        try:
            if self.live:
                try:
                    self.live.stop()
                except:
                    pass
            
            self.setup(self.processing_stats['total_symbols'])
            if self.layout and not self.live:
                self.live = Live(self.layout, refresh_per_second=2, screen=True)
                self.start()
                logger.info("UI sorun sonrası yeniden başlatıldı")
        except Exception as e:
            logger.error(f"UI yeniden başlatılırken hata: {e}")
    
    def _update_prices_for_active_items(self, positions: List[Dict]):
        """Aktif sinyaller ve pozisyonlar için fiyatları güncelle"""
        # Güncelleme gereken sembollerin listesini oluştur
        symbols_to_update = set()
        
        # Açık pozisyonlar için sembolleri ekle
        for pos in positions:
            symbols_to_update.add(pos['symbol'])
        
        # Aktif sinyaller için sembolleri ekle
        for signal in self.active_signals:
            symbols_to_update.add(signal['symbol'])
        
        # Her sembol için fiyat güncelleme
        for symbol in symbols_to_update:
            try:
                # Son fiyatı doğrudan API'den alma
                fresh_price = self._get_fresh_price_from_api(symbol)
                
                if fresh_price > 0:
                    # Fiyat önbelleğini güncelle
                    self.symbol_price_cache[symbol] = fresh_price
                    self.price_update_times[symbol] = time.time()
                    
                    # İzlenen kripto verilerini güncelle
                    if symbol in self.target_cryptos:
                        self.target_cryptos[symbol]['last_price'] = fresh_price
                    
                    # Aktif sinyallerdeki fiyatları güncelle
                    for signal in self.active_signals:
                        if signal['symbol'] == symbol:
                            # Burada sadece last_price değerini güncelliyoruz, 
                            # original price değeri ilk yakalama fiyatı olduğundan değişmiyor
                            # Böylece değişim yüzdesi doğru hesaplanabilir
                            signal['current_price'] = fresh_price
            except Exception as e:
                logger.debug(f"{symbol} için fiyat güncellenirken hata: {e}")
    
    def _get_fresh_price_from_api(self, symbol: str) -> float:
        """Doğrudan API'den güncel fiyat almaya çalışır"""
        try:
            # Risk Manager üzerinden açık pozisyonlarda kontrol et
            if self.risk_manager and hasattr(self.risk_manager, 'get_position_for_symbol'):
                position = self.risk_manager.get_position_for_symbol(symbol)
                if position:
                    return position['mark_price']
            
            # Binance Client üzerinden doğrudan API ile fiyat alma
            if self.risk_manager and hasattr(self.risk_manager, 'client'):
                try:
                    # Senkron olarak API'den mark price al
                    price = self.risk_manager.client.client.futures_mark_price(symbol=symbol)
                    if isinstance(price, dict) and 'markPrice' in price:
                        return float(price['markPrice'])
                    elif isinstance(price, list) and len(price) > 0 and 'markPrice' in price[0]:
                        return float(price[0]['markPrice'])
                except:
                    # Hata durumunda diğer yöntemi dene
                    pass
            
            # Market Data üzerinden kontrol et
            if self.market_data and hasattr(self.market_data, 'client'):
                try:
                    client = self.market_data.client
                    if hasattr(client, 'get_mark_price'):
                        # Asenkron API call 
                        future = asyncio.run_coroutine_threadsafe(
                            client.get_mark_price(symbol),
                            asyncio.get_event_loop()
                        )
                        mark_price = future.result(timeout=2.0)  # 2 saniye timeout
                        if mark_price > 0:
                            return mark_price
                except:
                    pass
            
            # Başarısız olursa önbellekteki değeri döndür
            if symbol in self.symbol_price_cache:
                return self.symbol_price_cache[symbol]
                
            return 0
        except Exception as e:
            logger.debug(f"API'den taze fiyat alırken hata: {e}")
            return 0
    
    def _update_header(self, daily_stats: Dict = None):
        """Update the header panel with bot status and summary."""
        total_pnl = 0
        pnl_pct = 0
        
        if daily_stats:
            total_pnl = daily_stats.get('total_pnl', 0)
            pnl_pct = daily_stats.get('pnl_percentage', 0)
        
        # Format PnL with color and sign
        pnl_style = "green" if total_pnl >= 0 else "red"
        pnl_sign = "+" if total_pnl >= 0 else ""
        pnl_text = f"{pnl_sign}{total_pnl:.2f} USDT ({pnl_sign}{pnl_pct:.2f}%)"
        
        # Current time
        current_time = datetime.now().strftime("%H:%M:%S")
        
        # Bot status indicator
        status_emoji = "⚡" if self.running else "⏸️"
        status_text = "ÇALIŞIYOR" if self.running else "DURAKLATILDI"
        status_style = "green" if self.running else "yellow"
        
        # Create header text
        header_text = Text()
        header_text.append(f" Durum: ", style="bold")
        header_text.append(f"{status_emoji} {status_text}", style=status_style)
        
        # Get the real balance from risk_manager if available
        real_balance = 0.00
        if self.risk_manager and hasattr(self.risk_manager, 'get_total_balance'):
            real_balance = self.risk_manager.get_total_balance()
        
        header_text.append(f"   │ Bakiye: {real_balance:.2f} USDT   │ PNL: ", style="bold")
        header_text.append(pnl_text, style=pnl_style)
        header_text.append(f"   │ {current_time} ", style="bold")
        
        # Create panel with title
        title = f"Binance Futures Trading Bot │ v{self.version}"
        if self.testnet:
            title += " [TEST MODE]"
            
        self.layout["header"].update(
            Panel(
                Align.center(header_text, vertical="middle"),
                title=title,
                title_align="center",
                border_style="blue",
                box=box.ROUNDED
            )
        )
    
    def _update_market_status(self, market_state: Dict):
        """Update market status panel."""
        market_status = Table.grid(padding=1)
        market_status.add_column(style="bold cyan")
        market_status.add_column()
        
        # Piyasa verilerini işle - eksik veriler için varsayılan değerler kullan
        # Bu kısımda market_state içinde veri yoksa varsayılan değerler gösteriyoruz
        market_state_value = market_state.get('market_state', 'UNKNOWN')
        volatility_state = market_state.get('volatility_state', 'UNKNOWN')
        btc_trend = market_state.get('btc_trend', 0)
        
        # Format trend with color
        trend_style = "green"
        if market_state_value == "BEARISH" or market_state_value == "SLIGHTLY_BEARISH":
            trend_style = "red"
        elif market_state_value == "NEUTRAL":
            trend_style = "yellow"
        
        # Format volatility with color
        volatility_style = "yellow"
        if volatility_state == "HIGH" or volatility_state == "EXTREME":
            volatility_style = "red bold"
        elif volatility_state == "LOW":
            volatility_style = "green"
        
        # BTC trend style
        btc_trend_value = "NEUTRAL"
        btc_trend_style = "yellow"
        if btc_trend > 30:
            btc_trend_value = "BULLISH"
            btc_trend_style = "green"
        elif btc_trend < -30:
            btc_trend_value = "BEARISH"
            btc_trend_style = "red"
        
        # Eksik veriler için makul varsayılan değerler
        btc_dominance = market_state.get('btc_dominance', 50.0)  # Yaklaşık BTC dominance değeri
        
        # Gainers hesaplama
        gainers_count = market_state.get('gainers_count', 0)
        total_symbols = market_state.get('total_symbols', 1)
        gainers_pct = (gainers_count / total_symbols * 100) if total_symbols > 0 else 50.0  # Yaklaşık değer
        
        # Volatilite ve funding değerleri
        volatility_24h = market_state.get('avg_volatility', 2.5)  # Ortalama volatilite
        funding_avg = market_state.get('avg_funding_rate', 0.01)  # Ortalama funding değeri
        btc_funding = market_state.get('btc_funding_rate', funding_avg)  # BTC funding değeri
        
        market_status.add_row("Trend:", Text(market_state_value, style=trend_style))
        market_status.add_row("Volatilite:", Text(volatility_state, style=volatility_style))
        market_status.add_row("BTC Dominance:", f"{btc_dominance:.1f}%")
        market_status.add_row("BTC Trend:", Text(btc_trend_value, style=btc_trend_style))
        market_status.add_row("1h Gainers:", f"{gainers_pct:.1f}%")
        market_status.add_row("Volatilite (24h):", f"{volatility_24h:.2f}%")
        market_status.add_row("Funding Ortalaması:", f"{funding_avg:.4f}%")
        market_status.add_row("BTC Funding:", f"{btc_funding:.4f}%")
        
        self.layout["market_status"].update(
            Panel(
                market_status,
                title="Piyasa Durumu",
                border_style="blue",
                box=box.ROUNDED
            )
        )
    
    def _update_performance(self, daily_stats: Dict):
        """Update performance metrics panel."""
        performance = Table.grid(padding=1)
        performance.add_column(style="bold cyan")
        performance.add_column()
        
        # Get daily stats
        daily_pnl = daily_stats.get('total_pnl', 0)
        win_count = daily_stats.get('win_count', 0)
        loss_count = daily_stats.get('loss_count', 0)
        trade_count = daily_stats.get('trade_count', 0)
        
        # Format with signs and colors
        daily_pnl_sign = "+" if daily_pnl >= 0 else ""
        daily_pnl_style = "green" if daily_pnl >= 0 else "red"
        
        # Format weekly stats
        weekly_pnl = self.weekly_stats['total_pnl']
        weekly_pnl_sign = "+" if weekly_pnl >= 0 else ""
        weekly_pnl_style = "green" if weekly_pnl >= 0 else "red"
        
        # Calculate win rate
        win_rate = 0
        if trade_count > 0:
            win_rate = (win_count / trade_count) * 100
        
        # Get real metrics from daily_stats or risk_manager if available
        avg_win = daily_stats.get('avg_win_pct', 0)
        avg_loss = daily_stats.get('avg_loss_pct', 0)
        drawdown = 0
        if self.risk_manager:
            drawdown = getattr(self.risk_manager, 'drawdown', 0)
        
        performance.add_row("Günlük P/L:", Text(f"{daily_pnl_sign}{daily_pnl:.2f} USDT", style=daily_pnl_style))
        performance.add_row("Haftalık P/L:", Text(f"{weekly_pnl_sign}{weekly_pnl:.2f} USDT", style=weekly_pnl_style))
        performance.add_row("Toplam İşlem:", f"{trade_count}")
        performance.add_row("Başarı Oranı:", f"{win_rate:.1f}% ({win_count}/{trade_count})")
        performance.add_row("Ort. Kazanç:", f"{avg_win:.2f}%")
        performance.add_row("Ort. Kayıp:", f"{avg_loss:.2f}%")
        performance.add_row("Drawdown:", f"{drawdown:.1f}%")
        
        # Risk level based on drawdown
        risk_level = "LOW"
        risk_style = "green"
        if drawdown > 5:
            risk_level = "HIGH"
            risk_style = "red"
        elif drawdown > 2:
            risk_level = "MODERATE"
            risk_style = "yellow"
            
        performance.add_row("Risk Seviyesi:", Text(risk_level, style=risk_style))
        
        self.layout["performance"].update(
            Panel(
                performance,
                title="Performans Metrikleri",
                border_style="blue",
                box=box.ROUNDED
            )
        )
    
    def _update_target_cryptos(self, top_symbols: List):
        """Update target cryptocurrencies monitoring panel."""
        # Create table for target cryptos
        table = Table(box=box.SIMPLE)
        table.add_column("Trend", justify="center", style="bold", width=6)
        table.add_column("Sym", justify="left", style="cyan", width=6)
        table.add_column("Fiyat", justify="right", width=10)
        table.add_column("Vol", justify="center", width=8)
        table.add_column("Güç", justify="right", width=5)
        table.add_column("Fırsat", justify="right", width=5)  # Fırsat puanı sütunu eklendi
        
        # Add rows for each target crypto
        for symbol, data in top_symbols:
            # Determine trend arrow
            trend = data.get('trend', 'NEUTRAL')
            trend_arrow = "●"  # neutral
            trend_style = "yellow"
            
            if trend == "LONG":
                trend_arrow = "▲"
                trend_style = "green"
            elif trend == "SHORT":
                trend_arrow = "▼"
                trend_style = "red"
            
            # Format volatility as stars
            volatility = data.get('volatility', 2)
            vol_stars = "★" * volatility + "☆" * (5 - volatility)
            
            # Format price - Güncel fiyatı API'den almaya çalış
            api_price = self._get_fresh_price_from_api(symbol)
            price = api_price if api_price > 0 else data.get('last_price', 0)
            
            # Format precision based on price magnitude
            if price < 0.001:
                price_str = f"{price:.8f}"
            elif price < 0.01:
                price_str = f"{price:.6f}"
            elif price < 0.1:
                price_str = f"{price:.5f}"
            elif price < 1:
                price_str = f"{price:.4f}"
            elif price < 100:
                price_str = f"{price:.3f}"
            elif price < 1000:
                price_str = f"{price:.2f}"
            else:
                price_str = f"{price:.1f}"
            
            # Signal strength
            signal_strength = data.get('signal_strength', 0)
            
            # Fırsat puanı
            opportunity_score = data.get('opportunity_score', 0)
            
            # Soğuma durumu (❄️ sembolü ile)
            cooling_indicator = ""
            if hasattr(self, 'market_data') and self.market_data and hasattr(self.market_data, 'target_pool'):
                is_cooling = self.market_data.target_pool.is_symbol_cooling_down(symbol)
                if is_cooling:
                    cooling_indicator = "❄️"
            
            # Fırsat puanına göre renk belirle
            opportunity_style = "white"
            if opportunity_score > 80:
                opportunity_style = "bright_green"
            elif opportunity_score > 60:
                opportunity_style = "green"
            elif opportunity_score < 30:
                opportunity_style = "red"
            
            table.add_row(
                Text(trend_arrow, style=trend_style),
                symbol.split("USDT")[0] if "USDT" in symbol else symbol,  # Remove USDT suffix
                price_str,
                vol_stars,
                f"{signal_strength:.0f}%",
                Text(f"{opportunity_score:.0f}{cooling_indicator}", style=opportunity_style)  # Fırsat puanı
            )
        
        # If no data, show empty but structured table
        if not top_symbols:
            table.add_row("", "", "", "", "", "")
        
        self.layout["target_cryptos"].update(
            Panel(
                table,
                title="Hedef Kriptopara İzleme",
                border_style="blue",
                box=box.ROUNDED
            )
        )
    
    def _update_positions(self, positions: List[Dict]):
        """Update open positions panel."""
        # Create table for positions
        table = Table(box=box.SIMPLE)
        table.add_column("Sym", justify="left", style="cyan", width=6)
        table.add_column("Yön", justify="center", style="bold", width=5)
        table.add_column("Miktar", justify="right", width=10)
        table.add_column("Margin", justify="right", width=8)
        table.add_column("Kaldıraç", justify="center", width=6)
        table.add_column("Giriş", justify="right", width=10)
        table.add_column("Güncel", justify="right", width=10)
        table.add_column("SL", justify="right", style="red", width=10)
        table.add_column("TP", justify="right", style="green", width=10)
        table.add_column("P/L", justify="right", width=8)
        
        # Add rows for each position
        for pos in positions:
            symbol = pos['symbol'].split("USDT")[0] if "USDT" in pos['symbol'] else pos['symbol']  # Remove USDT suffix
            side = pos['side']
            amount = abs(pos['amount'])
            entry_price = pos['entry_price']
            
            # Get leverage from position or default to 1
            leverage = pos.get('leverage', 1)
            
            # Calculate margin (USDT value of position without leverage)
            margin = (amount * entry_price) / leverage
            
            # Güncel fiyatı al - doğrudan API'den
            mark_price = self._get_fresh_price_from_api(pos['symbol'])
            if mark_price <= 0:
                mark_price = pos['mark_price']  # API'den alınamazsa pozisyondaki değeri kullan
            
            # Önbelleğe pozisyon fiyatını ekle/güncelle
            self.symbol_price_cache[pos['symbol']] = mark_price
            self.price_update_times[pos['symbol']] = time.time()
            
            # Get stop loss price if available, otherwise estimate
            sl_price = pos.get('stop_loss', 0)
            if sl_price == 0:
                # Fallback to estimate if not provided
                if side == "LONG":
                    sl_price = entry_price * 0.97  # Estimate: 3% below entry
                else:
                    sl_price = entry_price * 1.03  # Estimate: 3% above entry
            
            # Get take profit price if available
            tp_price = 0
            # Try to get TP from position_manager if available
            if self.position_manager and hasattr(self.position_manager, 'take_profit_orders'):
                if pos['symbol'] in self.position_manager.take_profit_orders:
                    tp_orders = self.position_manager.take_profit_orders[pos['symbol']]
                    if tp_orders and len(tp_orders) > 0:
                        # Use the first TP level
                        tp_price = tp_orders[0].get('price', 0)
            
            # If no TP price, estimate
            if tp_price == 0:
                # Estimate based on strategy settings
                tp_percent = 2.0  # Default: 2%
                if self.risk_manager and hasattr(self.risk_manager, 'strategy'):
                    tp_targets = self.risk_manager.strategy.get('take_profit_targets', [2.0])
                    if tp_targets and len(tp_targets) > 0:
                        tp_percent = tp_targets[0]
                
                if side == "LONG":
                    tp_price = entry_price * (1 + (tp_percent / 100))
                else:  # SHORT
                    tp_price = entry_price * (1 - (tp_percent / 100))
            
            # Calculate P/L - mark_price değiştiği için yeniden hesapla
            if side == "LONG":
                pnl = (mark_price - entry_price) * amount
            else:  # SHORT
                pnl = (entry_price - mark_price) * amount
                
            pnl_style = "green" if pnl >= 0 else "red"
            pnl_sign = "+" if pnl >= 0 else ""
            
            # Format based on side
            side_style = "green" if side == "LONG" else "red"
            
            # Format numbers with more precision
            amount_str = f"{amount:.6f}"
            entry_price_str = self._format_price(entry_price)
            mark_price_str = self._format_price(mark_price)
            sl_price_str = self._format_price(sl_price)
            tp_price_str = self._format_price(tp_price)
            
            table.add_row(
                symbol,
                Text(side, style=side_style),
                amount_str,
                f"{margin:.2f}",
                f"{leverage}x",
                entry_price_str,
                mark_price_str,
                sl_price_str,
                tp_price_str,
                Text(f"{pnl_sign}{pnl:.2f}", style=pnl_style)
            )
        
        # Calculate actual risk from risk_manager if available
        total_risk = 0
        max_risk = 10.0
        
        if self.risk_manager and hasattr(self.risk_manager, '_calculate_total_account_risk'):
            total_risk = self.risk_manager._calculate_total_account_risk()
            
            # risk_manager.strategy kullanıyoruz
            if hasattr(self.risk_manager, 'strategy'):
                max_risk = self.risk_manager.strategy.get('max_account_risk', 10.0)
        
        risk_pct = (total_risk / max_risk) * 100 if max_risk > 0 else 0
        risk_style = "green"
        if risk_pct > 70:
            risk_style = "red bold"
        elif risk_pct > 40:
            risk_style = "yellow"
        
        # Add risk information footer
        risk_text = Text()
        risk_text.append("\nToplam Risk Seviyesi: ")
        risk_text.append(f"{total_risk:.1f}% / {max_risk:.1f}%", style=risk_style)
        
        # Combine table and footer
        content = Group(table, risk_text)
        
        self.layout["positions"].update(
            Panel(
                content,
                title=f"Açık Pozisyonlar ({len(positions)}/{self.processing_stats['max_positions']})",
                border_style="blue",
                box=box.ROUNDED
            )
        )
    
    def _format_price(self, price: float) -> str:
        """Fiyatı doğru hassasiyette formatlar"""
        if price == 0:
            return "0.00"
            
        # Format precision based on price magnitude
        if price < 0.001:
            return f"{price:.8f}"
        elif price < 0.01:
            return f"{price:.6f}"
        elif price < 0.1:
            return f"{price:.5f}"
        elif price < 1:
            return f"{price:.4f}"
        elif price < 100:
            return f"{price:.3f}"
        elif price < 1000:
            return f"{price:.2f}"
        else:
            return f"{price:.1f}"
    
    def _update_signals(self, signals: List[Dict]):
        """Update signals panel with both original and current prices."""
        # Create table for signals
        table = Table(box=box.SIMPLE)
        table.add_column("Sym", justify="left", style="cyan", width=6)
        table.add_column("Sinyal", justify="center", style="bold", width=8)
        table.add_column("İlk Fiyat", justify="right", width=10)
        table.add_column("Güncel", justify="right", width=10)
        table.add_column("Δ%", justify="center", width=5)  # Delta yüzdesi
        table.add_column("Güç", justify="center", width=5)
        table.add_column("Tahmini İşlem", justify="left", width=14)
        
        # Filter and sort signals by strength
        tradable_signals = [s for s in signals if s.get('tradable', False)]
        tradable_signals.sort(key=lambda x: x.get('signal_strength', 0), reverse=True)
        
        # Take top signals
        for signal in tradable_signals[:5]:
            symbol = signal['symbol'].split("USDT")[0] if "USDT" in signal['symbol'] else signal['symbol']  # Remove USDT suffix
            signal_type = signal['signal']
            
            # Original capture price 
            original_price = signal['last_price']
            
            # Get current price (API'den taze veri al)
            current_price = self._get_fresh_price_from_api(signal['symbol'])
            if current_price <= 0:
                # API'den alınamazsa sinyal verisini kontrol et
                current_price = signal.get('current_price', original_price)  
                
                # Hala yoksa son kayıtlı fiyatı kullan
                if current_price <= 0:
                    current_price = original_price
            
            # Sinyal verisini güncelle - sonraki hesaplamalar için
            signal['current_price'] = current_price
            
            # Calculate price change
            if original_price > 0:
                price_change_pct = ((current_price - original_price) / original_price) * 100
            else:
                price_change_pct = 0
                
            # Format price change with arrow and color
            if price_change_pct > 0:
                delta_text = f"↑{price_change_pct:.1f}"
                delta_style = "green"
            elif price_change_pct < 0:
                delta_text = f"↓{abs(price_change_pct):.1f}"
                delta_style = "red"
            else:
                delta_text = "0.0"
                delta_style = "yellow"
                
            strength = signal['signal_strength']
            
            # Format signal type
            signal_style = "green" if signal_type == "LONG" else "red"
            
            # Format expected action based on position sizing algorithm
            expected_amount = self._calculate_expected_amount(signal)
            expected_margin = (expected_amount * current_price) 
            if self.risk_manager and hasattr(self.risk_manager, 'strategy'):
                leverage = self.risk_manager.strategy.get('default_leverage', 5)
                expected_margin /= leverage
                
            action_prefix = "Alım: +" if signal_type == "LONG" else "Satış: -"
            expected_action = f"{action_prefix}{expected_amount:.6f} ({expected_margin:.1f}$)"
            
            # Soğuma durumu kontrolü
            cooling_status = ""
            if hasattr(self, 'market_data') and self.market_data:
                if hasattr(self.market_data, 'target_pool'):
                    if self.market_data.target_pool.is_symbol_cooling_down(signal['symbol']):
                        cooling_status = " ❄️"  # Soğuma işareti
            
            original_price_str = self._format_price(original_price)
            current_price_str = self._format_price(current_price)
            
            table.add_row(
                symbol,
                Text(signal_type, style=signal_style),
                original_price_str,
                current_price_str,
                Text(delta_text, style=delta_style),
                f"{strength:.0f}%",
                expected_action + cooling_status  # Soğuma durumu eklendi
            )
        
        # Add monitoring signals
        monitoring_signals = [s for s in signals if not s.get('tradable', False)][:3]
        
        for signal in monitoring_signals:
            symbol = signal['symbol'].split("USDT")[0] if "USDT" in signal['symbol'] else signal['symbol']
            original_price = signal['last_price']
            
            # Get current price (API'den taze veri al)
            current_price = self._get_fresh_price_from_api(signal['symbol'])
            if current_price <= 0:
                # API'den alınamazsa sinyal verisini kontrol et
                current_price = signal.get('current_price', original_price)
                
                # Hala yoksa son kayıtlı fiyatı kullan
                if current_price <= 0:
                    current_price = original_price
            
            # Sinyal verisini güncelle - sonraki hesaplamalar için
            signal['current_price'] = current_price
            
            strength = signal['signal_strength']
            
            # Calculate price change
            if original_price > 0:
                price_change_pct = ((current_price - original_price) / original_price) * 100
            else:
                price_change_pct = 0
                
            # Format price change
            if price_change_pct > 0:
                delta_text = f"↑{price_change_pct:.1f}"
                delta_style = "green"
            elif price_change_pct < 0:
                delta_text = f"↓{abs(price_change_pct):.1f}"
                delta_style = "red"
            else:
                delta_text = "0.0"
                delta_style = "yellow"
            
            # Different status based on strength
            status = "WAITING"
            status_text = "Onay bekliyor..."
            
            if strength < 50:
                status = "MONITOR"
                status_text = "RSI izleniyor"
            elif strength < 60:
                status = "WATCHING"
                status_text = "Trend takip ediliyor"
            
            # Fırsat puanını kontrol et
            opportunity_score = 0
            if hasattr(self, 'market_data') and self.market_data:
                if hasattr(self.market_data, 'target_pool'):
                    target_data = self.market_data.target_pool.get_target_data(signal['symbol'])
                    if target_data and 'score' in target_data:
                        opportunity_score = target_data['score']
                        
                        # Yüksek fırsat puanı varsa vurgulanmış durum göster
                        if opportunity_score > 70:
                            status = "HIGH OPP"
                            status_text = f"Yüksek Fırsat: {opportunity_score:.0f}%"
            
            original_price_str = self._format_price(original_price)
            current_price_str = self._format_price(current_price)
            
            table.add_row(
                symbol,
                Text(status, style="yellow"),
                original_price_str,
                current_price_str,
                Text(delta_text, style=delta_style),
                f"{strength:.0f}%",
                status_text
            )
        
        # If no signals, show empty but structured table
        if not signals:
            table.add_row("", "", "", "", "", "", "")
        
        # Sonraki güncellemeyi zorla (fiyat değişimleri için)
        self.force_price_update = True
        
        self.layout["signals"].update(
            Panel(
                table,
                title="İşlem Bekleyen Sinyaller",
                border_style="blue",
                box=box.ROUNDED
            )
        )
    
    def _get_current_price(self, symbol: str) -> float:
        """Sembol için güncel fiyatı döndürür (iyileştirilmiş)."""
        current_time = time.time()
        
        # Önce doğrudan API'den taze veri almayı dene
        fresh_price = self._get_fresh_price_from_api(symbol)
        if fresh_price > 0:
            # API'den taze veri alındıysa önbelleği güncelle ve döndür
            self.symbol_price_cache[symbol] = fresh_price
            self.price_update_times[symbol] = current_time
            return fresh_price
        
        # Eğer API'den veri alamadıysak önbelleği kontrol et
        if symbol in self.symbol_price_cache:
            last_update_time = self.price_update_times.get(symbol, 0)
            
            # Önbellek süresini azalt - 5 saniye
            if current_time - last_update_time < 5:
                return self.symbol_price_cache[symbol]
        
        # API'den veri alınamadı ve önbellek de süresi geçmişse
        # hedef kriptolar listesine bak
        if symbol in self.target_cryptos:
            return self.target_cryptos[symbol].get('last_price', 0)
        
        # Hiçbir veri kaynağında bulunamadıysa 0 döndür
        return 0
    
    def _calculate_expected_amount(self, signal: Dict) -> float:
        """Sinyal için beklenen işlem miktarını hesaplar (iyileştirilmiş)."""
        # Bakiye ve sinyal gücüne göre hesaplama yapalım
        if self.risk_manager:
            try:
                # Hesap bakiyesini al
                balance = self.risk_manager.get_available_balance()
                
                # Risk parametrelerini al
                if hasattr(self.risk_manager, 'strategy'):
                    account_risk = self.risk_manager.strategy.get('account_risk_per_trade', 1.5) / 100
                    default_leverage = self.risk_manager.strategy.get('default_leverage', 5)
                else:
                    account_risk = 0.015  # Varsayılan %1.5 risk
                    default_leverage = 5   # Varsayılan 5x kaldıraç
                
                # Sinyal gücü faktörü
                signal_strength = signal.get('signal_strength', 50) / 100
                
                # Fırsat puanı faktörü (eğer varsa)
                opportunity_factor = 1.0
                if hasattr(self, 'market_data') and self.market_data:
                    if hasattr(self.market_data, 'target_pool'):
                        target_data = self.market_data.target_pool.get_target_data(signal['symbol'])
                        if target_data and 'score' in target_data:
                            opportunity_score = target_data['score']
                            # Fırsat puanına göre %0-30 arası bonus
                            opportunity_factor = 1.0 + ((opportunity_score - 50) / 100)
                            opportunity_factor = max(0.8, min(1.3, opportunity_factor))
                
                # Pozisyon büyüklüğü hesaplaması
                risk_amount = balance * account_risk
                
                # Hesaplanan pozisyon boyutu (USDT)
                position_size_usdt = risk_amount * default_leverage * signal_strength * opportunity_factor
                
                # Coin miktarını hesapla (yaklaşık)
                price = signal.get('current_price', signal.get('last_price', 0))
                if price <= 0:
                    return 0
                
                coin_amount = position_size_usdt / price
                
                # Makul sınırlar içinde kal
                max_coin = balance * 0.25 / price  # Balance'ın maksimum %25'i
                coin_amount = min(coin_amount, max_coin)
                
                return coin_amount
            except Exception as e:
                logger.debug(f"Beklenen işlem miktarı hesaplanırken hata: {e}")
                # Hata olursa fallback hesaplama
        
        # Fallback hesaplama - çok basit tahmin
        base_amount = 0.01  # Temel miktar
        strength_factor = signal.get('signal_strength', 50) / 50  # Normalize edilmiş güç faktörü
        
        return base_amount * strength_factor
    
    def _update_activity_log(self):
        """Update activity log panel."""
        # Create table for activity log
        table = Table(box=None, show_header=False, padding=(0, 1))
        table.add_column(style="bright_black", width=9)  # timestamp
        table.add_column(width=2)  # emoji
        table.add_column()  # message
        table.add_column(style="bright_black")  # details
        
        # Get latest activities (show max 4 in this panel)
        recent_activities = self.activity_log[-4:] if self.activity_log else []
        
        # Add rows for each activity
        for activity in recent_activities:
            timestamp = activity.get("timestamp", "")
            emoji = activity.get("emoji", "•")
            message = activity.get("message", "")
            
            # Format details based on activity type
            details = ""
            activity_type = activity.get("type", "")
            data = activity.get("data", {})
            
            if activity_type == "TRADE_CLOSE":
                pnl = data.get("pnl", 0)
                pnl_style = "green" if pnl >= 0 else "red"
                details = f"Kâr: {'+' if pnl >= 0 else ''}{pnl:.2f} USDT"
            elif activity_type == "SL_UPDATE":
                details = f"Trailing stop aktif"
            elif activity_type == "TRADE_OPEN":
                details = f"Sebep: {data.get('reason', 'N/A')}"
            elif activity_type == "SIGNAL":
                details = f"RSI: {data.get('rsi', 'N/A')}, MACD {data.get('macd', 'N/A')}"
            elif activity_type == "OPPORTUNITY":
                details = f"Fırsat Puanı: {data.get('score', 'N/A')}"
            elif activity_type == "COOLING":
                details = f"Soğuma: {data.get('duration', 'N/A')} dk"
            
            table.add_row(
                timestamp,
                emoji,
                message,
                details
            )
        
        # If no real activities yet, show empty panel without demo data
        if not recent_activities:
            table.add_row("", "", "Henüz işlem kaydı bulunmuyor", "")
        
        self.layout["activity"].update(
            Panel(
                table,
                title="Son İşlemler / Aktiviteler",
                border_style="blue",
                box=box.ROUNDED
            )
        )
    
    def _update_bot_status(self):
        """Update bot status panel."""
        table = Table.grid(padding=1)
        table.add_column(style="bold")
        table.add_column()
        
        # System health checks
        api_status = "✓ " if self.system_stats['api_connected'] else "✗ "
        api_style = "green" if self.system_stats['api_connected'] else "red"
        
        market_data = "✓ " if self.system_stats['market_data_flow'] == 'Normal' else "⚠ "
        market_style = "green" if self.system_stats['market_data_flow'] == 'Normal' else "yellow"
        
        risk_limits = "✓ " if self.system_stats['risk_limits_ok'] else "✗ "
        risk_style = "green" if self.system_stats['risk_limits_ok'] else "red"
        
        memory_usage = self.system_stats['memory_usage']
        memory_style = "green"
        if memory_usage > 1000:
            memory_style = "red"
        elif memory_usage > 500:
            memory_style = "yellow"
        
        cpu_usage = self.system_stats['cpu_usage']
        cpu_style = "green"
        if cpu_usage > 80:
            cpu_style = "red"
        elif cpu_usage > 60:
            cpu_style = "yellow"
        
        # Add rows
        table.add_row(Text(f"{api_status}Binance API Bağlantısı:", style=api_style), Text("Aktif", style=api_style))
        table.add_row(Text(f"{market_data}Piyasa Veri Akışı:", style=market_style), Text(self.system_stats['market_data_flow'], style=market_style))
        table.add_row(Text(f"{risk_limits}Risk Limitleri:", style=risk_style), Text("Uygun", style=risk_style))
        table.add_row(Text("✓ Sistem Bellek:", style=memory_style), Text(f"{memory_usage:.0f} MB", style=memory_style))
        table.add_row(Text(f"{'⚠ ' if cpu_usage > 60 else '✓ '}Sistem CPU:", style=cpu_style), Text(f"{cpu_usage:.0f}% {('(Yüksek)' if cpu_usage > 60 else '')}", style=cpu_style))
        
        self.layout["bot_status"].update(
            Panel(
                table,
                title="Bot Durumu Kontrolleri",
                border_style="blue",
                box=box.ROUNDED
            )
        )
    
    def _update_statistics(self):
        """Update statistics panel."""
        # Calculate runtime
        runtime = datetime.now() - self.start_time
        hours, remainder = divmod(runtime.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        runtime_str = f"{int(hours)}s {int(minutes)}d {int(seconds)}s"
        
        table = Table.grid(padding=1)
        table.add_column(style="bold")
        table.add_column()
        
        # Add statistics
        table.add_row("İşlenen Sembol Sayısı:", f"{self.processing_stats['processed_symbols']}/{self.processing_stats['total_symbols']}")
        table.add_row("Üretilen Sinyal Sayısı:", f"{self.processing_stats['signals_generated']}")
        
        # Open positions count - safely get from attribute if it exists
        open_pos_count = 0
        max_pos = self.processing_stats['max_positions']
        if self.risk_manager:
            open_pos_count = len(getattr(self.risk_manager, 'open_positions', []))
        elif hasattr(self, 'position_manager'):
            open_pos_count = len(getattr(self.position_manager, 'active_trades', {}))
        
        table.add_row("Açık Pozisyon:", f"{open_pos_count}/{max_pos}")
        table.add_row("Ortalama Sinyal Gücü:", f"{self.processing_stats['avg_signal_strength']:.1f}%")
        
        # Most active symbol - FIX: Limit the signal count to avoid incorrect large numbers
        most_active = self.processing_stats['most_active_symbol']
        most_active_count = min(self.processing_stats['most_active_count'], 30)  # Sınırla, makul bir sayı olsun
        
        if most_active:
            table.add_row("En Aktif Sembol:", f"{most_active.replace('USDT', '')} (+{most_active_count} sinyal)")
        else:
            table.add_row("En Aktif Sembol:", "N/A")
        
        # Dinamik hedef havuzu istatistikleri
        if hasattr(self, 'market_data') and self.market_data and hasattr(self.market_data, 'target_pool'):
            evaluated_symbols = len(self.market_data.target_pool.targets)
            cooling_symbols = sum(1 for symbol in self.market_data.target_pool.targets 
                                if self.market_data.target_pool.is_symbol_cooling_down(symbol))
            
            table.add_row("Değerlendirilen Semboller:", f"{evaluated_symbols}")
            table.add_row("Soğuma Sürecindeki Semboller:", f"{cooling_symbols}")
            
            # Sembol başarı oranı
            success_count = len(self.market_data.target_pool.success_history)
            failure_count = len(self.market_data.target_pool.attempt_failures)
            if success_count + failure_count > 0:
                success_rate = (success_count / (success_count + failure_count)) * 100
                table.add_row("Sembol Başarı Oranı:", f"{success_rate:.1f}%")
        
        # Runtime display
        table.add_row("Çalışma Süresi:", runtime_str)
        
        self.layout["statistics"].update(
            Panel(
                table,
                title=f"İstatistikler ({int(hours)}s {int(minutes)}d)",
                border_style="blue",
                box=box.ROUNDED
            )
        )