"""
Trading Bot main application entry point
"""

import sys
import os
import time
import asyncio
import logging
import traceback
import signal
import random
from datetime import datetime
import aiofiles

from trading_bot.config import API_KEY, API_SECRET, USE_TESTNET, setup_logging, load_config
from trading_bot.api.binance_client import BinanceClient
from trading_bot.core.strategy import StrategyParams
from trading_bot.core.market_data import MarketDataManager
from trading_bot.core.signal import SignalGenerator
from trading_bot.core.risk import RiskManager
from trading_bot.core.position import PositionManager
from trading_bot.utils.ui import BotUI

# Set up loggers
logger, api_logger, trade_logger, perf_logger = setup_logging()

class TradingBot:
    """Ana trading bot sınıfı."""
    
    def __init__(self, api_key: str, api_secret: str, config_file=None, testnet=False):
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.config_file = config_file
        
        # Konfigürasyon yükle
        config = load_config(config_file)
        
        # Ana bileşenleri oluştur
        self.strategy = StrategyParams(config)
        self.client = BinanceClient(api_key, api_secret, testnet)
        self.market_data = MarketDataManager(self.client, self.strategy)
        self.risk_manager = RiskManager(self.client, self.strategy)
        self.signal_generator = SignalGenerator(self.market_data, self.strategy)
        self.position_manager = PositionManager(self.client, self.risk_manager, self.strategy)
        
        # UI konsolu
        self.ui = BotUI(testnet)
        
        # Başlatma ve durum değişkenleri
        self.running = False
        self.initialized = False
        self.tasks = []
        self.check_symbols = []
        
        # Alt sistemlerin kapatılması için event
        self.shutdown_event = asyncio.Event()
    
    async def initialize(self):
        """Trading bot'u başlatır ve bileşenleri hazırlar."""
        try:
            logger.info("Trading Bot başlatılıyor...")
            
            # Sinyal yönetici
            if sys.platform != 'win32':
                for s in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
                    asyncio.get_event_loop().add_signal_handler(
                        s, lambda s=s: asyncio.create_task(self.shutdown(s))
                    )
            
            # Piyasa verilerini hazırla
            await self.market_data.initialize()
            
            # Risk yöneticisini başlat
            await self.risk_manager.initialize()
            
            # İşlem yapılacak sembolleri bul
            self.check_symbols = await self.market_data.get_filtered_symbols()
            
            # İşlem yapılacak sembol yoksa uyarı ver
            if not self.check_symbols:
                logger.warning("İşlem yapılacak sembol bulunamadı. Minimum hacim ve whitelist/blacklist ayarlarını kontrol edin.")
                symbols = await self.market_data.get_filtered_symbols(min_volume=0)
                logger.info(f"Tüm semboller: {symbols}")
            else:
                logger.info(f"İşlem yapılacak semboller: {len(self.check_symbols)} adet")
                logger.debug(f"Semboller: {', '.join(self.check_symbols[:20])}" + 
                           (f" ve {len(self.check_symbols) - 20} adet daha..." if len(self.check_symbols) > 20 else ""))
            
            # UI'ı başlat
            try:
                self.ui.setup(len(self.check_symbols))
                
                # ÖNEMLI: UI için bileşen referanslarını ayarla
                # UI'a risk_manager ve market_data referansları
                self.ui.risk_manager = self.risk_manager
                self.ui.market_data = self.market_data
                
                # UI referanslarını diğer bileşenlere ilet
                self.risk_manager.ui = self.ui
                self.market_data.ui = self.ui
                self.signal_generator.ui = self.ui
                self.position_manager.ui = self.ui
                
                # UI'yi başlat
                self.ui.start()
                logger.info("UI başarıyla başlatıldı")
            except Exception as e:
                logger.error(f"UI başlatılırken hata: {e}")
                print(f"UI başlatılamadı: {e}")
                print("Bot, UI olmadan konsol modunda çalışmaya devam edecek.")
            
            # Initialized durumunu güncelle
            self.initialized = True
            logger.info("Trading Bot başlatıldı ve hazır.")
            
            return True
        except Exception as e:
            logger.error(f"Bot başlatılırken hata: {e}\n{traceback.format_exc()}")
            await self.shutdown()
            return False
    
    async def start(self):
        """Trading bot'u çalıştırır."""
        if not self.initialized:
            success = await self.initialize()
            if not success:
                return
        
        self.running = True
        
        logger.info("Trading Bot çalışıyor, işlemler aktif.")
        
        # Görevleri başlat
        self.tasks.append(asyncio.create_task(self._main_loop()))
        self.tasks.append(asyncio.create_task(self._market_update_loop()))
        self.tasks.append(asyncio.create_task(self._position_monitor_loop()))
        self.tasks.append(asyncio.create_task(self._ui_update_loop()))
        self.tasks.append(asyncio.create_task(self._health_check_loop()))
        
        # Tüm görevlerin tamamlanmasını bekle
        try:
            await self.shutdown_event.wait()
            logger.info("Kapatma sinyali alındı, görevler sonlandırılıyor...")
            
            # Bekleyen tüm görevleri iptal et
            for task in self.tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            
            # UI'ı kapat
            try:
                self.ui.stop()
            except Exception as e:
                logger.error(f"UI kapatılırken hata: {e}")
            
            # Binance client'ı kapat
            await self.client.close()
            
            logger.info("Trading Bot düzgün şekilde kapatıldı.")
            
        except Exception as e:
            logger.error(f"Trading Bot çalışırken beklenmeyen hata: {e}\n{traceback.format_exc()}")
            # Yine de kaynakları temizlemeye çalış
            try:
                self.ui.stop()
            except:
                pass
            await self.client.close()
    
    async def _main_loop(self):
        """Ana kontrol döngüsü, sembol kontrolü ve sinyal işleme."""
        try:
            # Fırsat değerlendirme döngüsünün çalışma durumu
            opportunity_evaluation_running = False
            initial_scan_complete = False
            
            while not self.shutdown_event.is_set():
                if not self.running:
                    await asyncio.sleep(1)
                    continue
                
                # İlk tam tarama henüz yapılmadıysa
                if not initial_scan_complete:
                    try:
                        logger.info("İlk fırsat taraması başlatılıyor...")
                        
                        # Hesap bilgilerini güncelle
                        await self.risk_manager.update_account_info()
                        
                        # Risk limitlerini kontrol et
                        if not await self.risk_manager.check_risk_limits():
                            logger.warning("Risk limitleri aşıldı, işlemler geçici olarak duraklatıldı")
                            await asyncio.sleep(60)  # 1 dakika bekle ve tekrar dene
                            continue
                        
                        # İşlem yapılacak sembolleri güncelle (eğer liste boşsa)
                        if not self.check_symbols:
                            self.check_symbols = await self.market_data.get_filtered_symbols()
                        
                        # Sembolleri daha küçük gruplara böl ve fırsat puanlarını hesapla
                        if self.check_symbols:
                            scan_batch_size = 20  # Her seferde 20 sembol tara
                            total_batches = (len(self.check_symbols) + scan_batch_size - 1) // scan_batch_size
                            
                            for batch_idx in range(total_batches):
                                if self.shutdown_event.is_set() or not self.running:
                                    break
                                    
                                start_idx = batch_idx * scan_batch_size
                                end_idx = min(start_idx + scan_batch_size, len(self.check_symbols))
                                current_batch = self.check_symbols[start_idx:end_idx]
                                
                                logger.info(f"Fırsat taraması: Batch {batch_idx+1}/{total_batches}, "
                                          f"{len(current_batch)} sembol taranıyor")
                                
                                # Sembollerin fırsat puanlarını hesapla ve güncelle
                                await self.market_data.refresh_symbol_opportunities(current_batch, True)
                                
                                # Batch'ler arasında biraz bekle (API yükünü azaltmak için)
                                await asyncio.sleep(2)
                            
                            logger.info(f"İlk fırsat taraması tamamlandı. {len(self.check_symbols)} sembol değerlendirildi.")
                            initial_scan_complete = True
                        else:
                            logger.warning("İşlem yapılacak sembol bulunamadı. Minimum hacim ve whitelist/blacklist ayarlarını kontrol edin.")
                            symbols = await self.market_data.get_filtered_symbols(min_volume=0)
                            logger.info(f"Tüm semboller: {symbols}")
                            await asyncio.sleep(60)  # 1 dakika bekle ve tekrar dene
                            continue
                    
                    except Exception as e:
                        logger.error(f"İlk fırsat taraması sırasında hata: {e}\n{traceback.format_exc()}")
                        await asyncio.sleep(30)  # 30 saniye bekle ve tekrar dene
                        continue
                
                # Ana işlem döngüsü - en iyi fırsatları değerlendir
                try:
                    # Hesap bilgilerini güncelle
                    await self.risk_manager.update_account_info()
                    
                    # Risk limitlerini kontrol et
                    if not await self.risk_manager.check_risk_limits():
                        logger.warning("Risk limitleri aşıldı, işlemler geçici olarak duraklatıldı")
                        await asyncio.sleep(60)  # 1 dakika bekle
                        continue
                    
                    # Piyasa durumunu kontrol et
                    market_state = await self.market_data.get_market_state()
                    
                    # Hafta sonu modu kontrolü
                    now = datetime.now()
                    is_weekend = now.weekday() >= 5  # 5=Cumartesi, 6=Pazar
                    
                    if not self.strategy.adapt_to_weekend(is_weekend):
                        logger.info("Hafta sonu modu aktif, işlemler duraklatıldı")
                        await asyncio.sleep(300)  # 5 dakika bekle
                        continue
                    
                    # Gün içi saat kontrolü
                    if not self.strategy.adapt_to_time_of_day():
                        logger.info("İşlem saatleri dışında, işlemler duraklatıldı")
                        await asyncio.sleep(300)  # 5 dakika bekle
                        continue
                    
                    # En iyi fırsatları al
                    top_opportunities = await self.market_data.get_top_opportunity_symbols(5)
                    
                    if not top_opportunities:
                        # Dinamik havuzda sembol yoksa, bazı sembolleri tara ve havuza ekle
                        random_symbols = self.check_symbols[:min(20, len(self.check_symbols))]
                        await self.market_data.refresh_symbol_opportunities(random_symbols, True)
                        
                        # Tekrar en iyi fırsatları al
                        top_opportunities = await self.market_data.get_top_opportunity_symbols(5)
                        
                        if not top_opportunities:
                            logger.info("İşlem yapılabilir fırsat bulunamadı, 30 saniye sonra tekrar denenecek")
                            await asyncio.sleep(30)
                            continue
                    
                    # Her bir fırsatı değerlendir
                    for symbol in top_opportunities:
                        try:
                            # Risk limitlerini tekrar kontrol et
                            if not await self.risk_manager.check_risk_limits():
                                break
                            
                            # Sembol için sinyal üret
                            signal = await self.signal_generator.generate_signal(symbol)
                            
                            if signal:
                                # İşlem girişimi yap
                                success = await self.position_manager.check_and_process_signal(
                                    symbol, signal, market_state['volatility_score']
                                )
                                
                                # İşlem sonucunu kaydet
                                if success:
                                    self.market_data.record_trade_success(symbol, {
                                        'signal_type': signal['signal'],
                                        'signal_strength': signal['signal_strength'],
                                        'timestamp': datetime.now()
                                    })
                                else:
                                    # signal['tradable'] True ama işlem başarısız olduysa
                                    if signal['tradable']:
                                        self.market_data.record_trade_attempt_failure(symbol, "İşlem girişimi başarısız")
                            
                        except Exception as e:
                            logger.error(f"{symbol} işlenirken hata: {e}")
                            self.market_data.record_trade_attempt_failure(symbol, f"Hata: {str(e)}")
                            continue
                    
                    # Arka planda fırsat puanlarını güncelle (eğer başka bir güncelleme çalışmıyorsa)
                    if not opportunity_evaluation_running and initial_scan_complete:
                        opportunity_evaluation_running = True
                        
                        try:
                            # Rastgele 10 sembol seç
                            # Sürekli farklı sembolleri değerlendirmek için
                            random_symbols = random.sample(self.check_symbols, min(10, len(self.check_symbols)))
                            
                            # Periyodik olarak tam yenileme yap
                            current_time = time.time()
                            do_full_refresh = (current_time % 3600) < 60  # Her saatin ilk dakikasında
                            
                            # Sembollerin fırsat puanlarını asenkron olarak güncelle
                            await self.market_data.refresh_symbol_opportunities(random_symbols, do_full_refresh)
                            
                        except Exception as e:
                            logger.error(f"Fırsat değerlendirme sırasında hata: {e}")
                        finally:
                            opportunity_evaluation_running = False
                    
                    # Gecikmeyi ayarla - işlem kontrolü için bekleme süresi
                    await asyncio.sleep(self.strategy.get('check_interval'))
                    
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"Ana döngüde beklenmeyen hata: {e}\n{traceback.format_exc()}")
                    await asyncio.sleep(10)  # Hata sonrası kısa bekleme
                
        except asyncio.CancelledError:
            logger.info("Ana kontrol döngüsü iptal edildi")
        except Exception as e:
            logger.error(f"Ana kontrol döngüsünde beklenmeyen hata: {e}\n{traceback.format_exc()}")
    
    async def _market_update_loop(self):
        """Piyasa verilerini düzenli olarak günceller."""
        try:
            while not self.shutdown_event.is_set():
                if not self.running:
                    await asyncio.sleep(1)
                    continue
                
                # BTC metriklerini her 5 dakikada bir güncelle
                await self.market_data.update_btc_metrics()
                
                # Genel piyasa metriklerini her 10 dakikada bir güncelle
                await self.market_data.update_market_metrics()
                
                # 5 dakika bekle
                await asyncio.sleep(300)
                
        except asyncio.CancelledError:
            logger.info("Piyasa güncelleme döngüsü iptal edildi")
        except Exception as e:
            logger.error(f"Piyasa güncelleme döngüsünde beklenmeyen hata: {e}\n{traceback.format_exc()}")
    
    async def _position_monitor_loop(self):
        """Açık pozisyonları izler ve gerekirse günceller."""
        try:
            while not self.shutdown_event.is_set():
                if not self.running:
                    await asyncio.sleep(1)
                    continue
                
                # Hesap bilgilerini güncelle
                await self.risk_manager.update_account_info()
                
                # Açık pozisyonları kontrol et
                for position in self.risk_manager.open_positions:
                    symbol = position['symbol']
                    current_price = position['mark_price']
                    
                    try:
                        # Trailing stop güncelle
                        await self.position_manager.update_trailing_stop(symbol, current_price)
                        
                        # Kısmi kar alma gerçekleştir
                        await self.position_manager.process_partial_close(symbol, current_price)
                    except Exception as e:
                        logger.error(f"{symbol} pozisyon izlenirken hata: {e}")
                
                # 10 saniye bekle
                await asyncio.sleep(10)
                
        except asyncio.CancelledError:
            logger.info("Pozisyon izleme döngüsü iptal edildi")
        except Exception as e:
            logger.error(f"Pozisyon izleme döngüsünde beklenmeyen hata: {e}\n{traceback.format_exc()}")
    
    async def _ui_update_loop(self):
        """UI'ı düzenli aralıklarla günceller."""
        try:
            ui_error_count = 0
            ui_last_error_time = 0
            
            while not self.shutdown_event.is_set():
                try:
                    # UI için verileri topla
                    positions = self.risk_manager.open_positions
                    signals = [self.signal_generator.signal_cache[s]['signal'] 
                             for s in self.signal_generator.signal_cache 
                             if self.signal_generator.signal_cache[s]['signal']['tradable']]
                    daily_stats = self.risk_manager.get_daily_stats()
                    market_state = await self.market_data.get_market_state()
                    
                    # İzlenen sembolleri al
                    watched_symbols = []
                    for symbol in self.check_symbols[:20]:  # Sadece ilk 20 sembolü dahil et
                        if symbol in self.signal_generator.signal_cache:
                            watched_symbols.append({"symbol": symbol, "last_price": self.signal_generator.signal_cache[symbol]['signal']['last_price']})
                    
                    # UI güncelle
                    self.ui.update(positions, signals, daily_stats, market_state, self.running, watched_symbols)
                    
                    # Hata sayacını sıfırla
                    ui_error_count = 0
                    
                except Exception as e:
                    current_time = time.time()
                    ui_error_count += 1
                    
                    # Her 10 hatada bir tam hata raporunu logla
                    if ui_error_count % 10 == 1 or current_time - ui_last_error_time > 300:  # 5 dakikada bir detaylı hata
                        logger.error(f"UI güncellenirken hata: {e}\n{traceback.format_exc()}")
                        ui_last_error_time = current_time
                    else:
                        logger.warning(f"UI güncellenirken hata: {e}")
                    
                    # Çok fazla UI hatası olursa UI'yi yeniden başlatmayı dene
                    if ui_error_count > 20:
                        try:
                            logger.info("UI çok fazla hata verdi, yeniden başlatılıyor...")
                            self.ui.stop()
                            self.ui = BotUI(self.testnet)
                            self.ui.setup(len(self.check_symbols))
                            self.ui.risk_manager = self.risk_manager
                            self.ui.market_data = self.market_data
                            self.ui.start()
                            ui_error_count = 0
                            logger.info("UI yeniden başlatıldı")
                        except Exception as restart_err:
                            logger.error(f"UI yeniden başlatılırken hata: {restart_err}")
                
                # 1 saniye bekle
                await asyncio.sleep(1)
                
        except asyncio.CancelledError:
            logger.info("UI güncelleme döngüsü iptal edildi")
        except Exception as e:
            logger.error(f"UI güncelleme döngüsünde beklenmeyen hata: {e}\n{traceback.format_exc()}")
    
    async def _health_check_loop(self):
        """Düzenli olarak sistem sağlık kontrolü yapar."""
        try:
            last_full_report_time = time.time()
            
            while not self.shutdown_event.is_set():
                try:
                    now = time.time()
                    
                    # Tam raporu her 1 saatte bir çalıştır
                    if now - last_full_report_time > self.strategy.get('health_check_interval'):
                        await self._generate_full_report()
                        last_full_report_time = now
                    
                    # API ve sistem durumunu kontrol et
                    await self._check_system_health()
                    
                except Exception as e:
                    logger.error(f"Sağlık kontrolü sırasında hata: {e}")
                
                # 5 dakika bekle
                await asyncio.sleep(300)
                
        except asyncio.CancelledError:
            logger.info("Sağlık kontrolü döngüsü iptal edildi")
        except Exception as e:
            logger.error(f"Sağlık kontrolü döngüsünde beklenmeyen hata: {e}\n{traceback.format_exc()}")
    
    async def _check_system_health(self):
        """Sistem sağlığını kontrol eder."""
        try:
            # API bağlantısını kontrol et
            try:
                server_time = await self.client.api_retry(self.client.client.get_server_time)
                server_time_diff = abs(int(server_time['serverTime']) - int(time.time() * 1000))
                
                if server_time_diff > 10000:  # 10 saniyeden fazla fark varsa
                    logger.warning(f"Sunucu saati ile yerel saat arasında büyük fark: {server_time_diff}ms")
            except Exception as e:
                logger.error(f"Sunucu saati kontrolünde hata: {e}")
            
            # Hesap durumunu kontrol et
            await self.risk_manager.update_account_info()
            
            # Memory kullanımını kontrol et
            try:
                import psutil
                process = psutil.Process(os.getpid())
                memory_info = process.memory_info()
                memory_usage_mb = memory_info.rss / 1024 / 1024
                
                if memory_usage_mb > 500:  # 500 MB'dan fazla bellek kullanımı
                    logger.warning(f"Yüksek bellek kullanımı: {memory_usage_mb:.2f} MB")
                
                # UI için sistem durumunu güncelle
                if hasattr(self.ui, 'system_stats'):
                    self.ui.system_stats['memory_usage'] = memory_usage_mb
                    self.ui.system_stats['cpu_usage'] = psutil.cpu_percent()
                    self.ui.system_stats['api_connected'] = True
                    
                logger.debug(f"Sistem sağlık kontrolü tamamlandı. Bellek kullanımı: {memory_usage_mb:.2f} MB")
            except ImportError:
                logger.warning("psutil modülü yüklü değil, bellek kullanımı izlenemiyor")
            
        except Exception as e:
            logger.error(f"Sistem sağlık kontrolünde hata: {e}")
    
    async def _generate_full_report(self):
        """Tam bir performans raporu oluşturur."""
        try:
            # Hesap bilgilerini güncelle
            await self.risk_manager.update_account_info()
            
            # Hesap değerleri
            total_balance = self.risk_manager.get_total_balance()
            available_balance = self.risk_manager.get_available_balance()
            initial_balance = self.risk_manager.initial_balance
            
            # Performans hesapla
            balance_change = total_balance - initial_balance
            balance_change_pct = (balance_change / initial_balance) * 100 if initial_balance > 0 else 0
            
            # Günlük istatistikler
            daily_stats = self.risk_manager.get_daily_stats()
            
            # Açık pozisyonlar
            open_positions = self.risk_manager.open_positions
            
            # Rapor oluştur
            report = f"""
📊 **PERFORMANS RAPORU**
📅 Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

💰 **Hesap Durumu**
  Toplam Bakiye: {total_balance:.2f} USDT
  Kullanılabilir: {available_balance:.2f} USDT
  Başlangıç: {initial_balance:.2f} USDT
  Toplam Değişim: {balance_change:.2f} USDT ({balance_change_pct:.2f}%)
  Drawdown: {self.risk_manager.drawdown:.2f}%

📈 **Günlük Performans**
  PNL: {daily_stats['total_pnl']:.2f} USDT ({daily_stats['pnl_percentage']:.2f}%)
  İşlemler: {daily_stats['trade_count']} (Kazanç: {daily_stats['win_count']}, Kayıp: {daily_stats['loss_count']})
  Kazanma Oranı: {daily_stats['win_rate']:.1f}%

🔄 **Açık Pozisyonlar: {len(open_positions)}**
"""
            # Açık pozisyonları ekle
            for pos in open_positions:
                symbol = pos['symbol']
                side = pos['side']
                amount = abs(pos['amount'])
                entry_price = pos['entry_price']
                mark_price = pos['mark_price']
                pnl = pos['pnl']
                pnl_pct = ((mark_price - entry_price) / entry_price) * 100 if side == "LONG" else ((entry_price - mark_price) / entry_price) * 100
                
                report += f"  {symbol}: {side} {amount:.4f} @ {entry_price:.6f} | PNL: {pnl:.2f} USDT ({pnl_pct:.2f}%)\n"
            
            # Raporlama
            logger.info(f"Performans raporu oluşturuldu:\n{report}")
            
            # Dosyaya kaydet
            report_file = f"./data/reports/report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            
            # reports dizini yoksa oluştur
            os.makedirs("./data/reports", exist_ok=True)
            
            async with aiofiles.open(report_file, 'w', encoding='utf-8') as f:
                await f.write(report)
            
            return report
        except Exception as e:
            logger.error(f"Performans raporu oluşturulurken hata: {e}")
            return None
    
    async def pause(self):
        """Bot çalışmasını duraklatır."""
        if self.running:
            self.running = False
            logger.info("Trading Bot duraklatıldı")
    
    async def resume(self):
        """Bot çalışmasını devam ettirir."""
        if not self.running:
            self.running = True
            logger.info("Trading Bot çalışmaya devam ediyor")
    
    async def shutdown(self, sig=None):
        """Bot'u güvenli bir şekilde kapatır."""
        if sig:
            logger.info(f"Sinyal alındı: {sig.name}, kapatılıyor...")
        else:
            logger.info("Kapatma isteği alındı")
        
        if self.running:
            self.running = False
        
        # Kapatma sinyalini gönder
        self.shutdown_event.set()


async def run_bot():
    """Bot'u çalıştırır."""
    # Parametre kontrolü
    if not API_KEY or not API_SECRET:
        print("Hata: API anahtarları tanımlanmamış. .env dosyasını kontrol edin.")
        return
    
    # Bot'u oluştur
    bot = TradingBot(
        api_key=API_KEY,
        api_secret=API_SECRET,
        testnet=USE_TESTNET,
        config_file=os.getenv("CONFIG_FILE")
    )
    
    # Bot'u başlat
    try:
        await bot.initialize()
        await bot.start()
    except KeyboardInterrupt:
        print("\nBot kullanıcı tarafından durduruldu.")
    except Exception as e:
        print(f"Hata: {e}")
    finally:
        # Bot bekleyen görevleri kontrol edildiğinden emin ol
        if not bot.shutdown_event.is_set():
            await bot.shutdown()


def main():
    """Ana fonksiyon."""
    try:
        # Python 3.11 ve üzeri için asyncio.run(run_bot())
        # Python 3.10 ve altı için aşağıdaki yöntem
        if sys.version_info >= (3, 11):
            asyncio.run(run_bot())
        else:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(run_bot())
    except KeyboardInterrupt:
        print("\nProgram kullanıcı tarafından sonlandırıldı.")
    except Exception as e:
        print(f"Hata: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()