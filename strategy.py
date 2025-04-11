"""
Strateji parametreleri ve yönetimi modülü
"""

import logging
from datetime import datetime
from typing import List, Dict, Any

logger = logging.getLogger("trading_bot")

class StrategyParams:
    """Strateji parametrelerini yöneten sınıf."""
    
    def __init__(self, params: Dict[str, Any]):
        self.params = params
        self.optimization_history = []  # Optimizasyon geçmişini tutmak için
        self.last_optimization_time = None  # Son optimizasyon zamanı
    
    def get(self, key: str, default=None):
        """Parametre değerini alır."""
        return self.params.get(key, default)
    
    def set(self, key: str, value: Any):
        """Parametre değerini ayarlar."""
        self.params[key] = value
        return value
    
    def update(self, param_dict: Dict[str, Any]):
        """Birden çok parametreyi günceller."""
        self.params.update(param_dict)
        return self.params
    
    def adapt_to_market_condition(self, volatility_index: float, trend_strength: float):
        """Piyasa koşullarına göre parametreleri uyarlar."""
        if not self.params.get('adaptive_params', False):
            return
        
        logger.info(f"Piyasa uyarlaması: Volatilite={volatility_index:.2f}, Trend Gücü={trend_strength:.2f}")
        
        # Volatiliteye göre stop loss ve take profit'i ayarla
        if volatility_index > 1.5:
            # Yüksek volatilite - daha geniş SL ve TP
            self.params['static_sl_percent'] *= volatility_index * 0.75
            self.params['trailing_sl_distance'] *= volatility_index * 0.75
            
            # TP hedeflerini artır
            new_tp_targets = [tp * (1 + (volatility_index - 1) * 0.5) for tp in self.params['take_profit_targets']]
            self.params['take_profit_targets'] = new_tp_targets
            
            logger.info(f"Yüksek volatilite ayarları: SL={self.params['static_sl_percent']:.2f}%, "
                       f"TP={[round(tp, 2) for tp in new_tp_targets]}%")
        elif volatility_index < 0.7:
            # Düşük volatilite - daha dar SL ve TP
            self.params['static_sl_percent'] *= max(0.5, volatility_index)
            self.params['trailing_sl_distance'] *= max(0.5, volatility_index)
            
            # TP hedeflerini azalt
            new_tp_targets = [tp * max(0.5, volatility_index) for tp in self.params['take_profit_targets']]
            self.params['take_profit_targets'] = new_tp_targets
            
            logger.info(f"Düşük volatilite ayarları: SL={self.params['static_sl_percent']:.2f}%, "
                       f"TP={[round(tp, 2) for tp in new_tp_targets]}%")
        
        # Trend gücüne göre pozisyon boyutunu ayarla
        trend_factor = max(0.5, min(2.0, trend_strength * self.params.get('trend_strength_factor', 1.0)))
        
        if trend_strength > 1.2:
            # Güçlü trend - daha yüksek pozisyon boyutu
            self.params['account_risk_per_trade'] *= trend_factor
            logger.info(f"Güçlü trend ayarları: Risk={self.params['account_risk_per_trade']:.2f}%")
        elif trend_strength < 0.8:
            # Zayıf trend - daha düşük pozisyon boyutu
            self.params['account_risk_per_trade'] /= (2 - trend_factor)
            logger.info(f"Zayıf trend ayarları: Risk={self.params['account_risk_per_trade']:.2f}%")
        
        # Parametre sınırlamalarını uygula
        self.params['account_risk_per_trade'] = min(self.params['account_risk_per_trade'], 
                                                  self.params.get('max_account_risk', 5.0) / 2)
        self.params['static_sl_percent'] = max(0.5, min(10.0, self.params['static_sl_percent']))
    
    def optimize_parameters(self, performance_history: List[Dict], market_condition: str):
        """Geçmiş performansa göre strateji parametrelerini otomatik optimize eder"""
        try:
            # Optimizasyon için yeterli veri yok
            if len(performance_history) < 10:
                logger.debug("Parametre optimizasyonu için yeterli veri yok (minimum 10 işlem gerekli)")
                return False
            
            # Sık sık optimizasyon yapmaktan kaçınmak için kontrol
            now = datetime.now()
            if self.last_optimization_time:
                hours_since_last_opt = (now - self.last_optimization_time).total_seconds() / 3600
                if hours_since_last_opt < 6:  # 6 saatten az geçmişse optimizasyon yapmayı atla
                    logger.debug(f"Son optimizasyondan bu yana {hours_since_last_opt:.1f} saat geçti, henüz yeni optimizasyon yapılmıyor")
                    return False
            
            # Son 10 işlemi analiz et
            win_trades = [trade for trade in performance_history[-10:] if trade.get('pnl', 0) > 0]
            loss_trades = [trade for trade in performance_history[-10:] if trade.get('pnl', 0) <= 0]
            
            win_rate = len(win_trades) / 10 if performance_history else 0
            
            # İyileştirilecek parametreleri kaydet
            original_params = {
                'static_sl_percent': self.params['static_sl_percent'],
                'trailing_sl_distance': self.params['trailing_sl_distance'],
                'min_score_to_trade': self.params['min_score_to_trade'],
                'account_risk_per_trade': self.params['account_risk_per_trade']
            }
            
            # Performans kötüyse parametreleri ayarla
            if win_rate < 0.4:
                # Daha muhafazakar ayarlar
                self.params['trailing_sl_distance'] = min(2.0, self.params['trailing_sl_distance'] * 1.2)
                self.params['static_sl_percent'] = min(3.0, self.params['static_sl_percent'] * 1.2)
                
                # Sinyal filtrelerini sıkılaştır
                self.params['min_score_to_trade'] += 5
                
                # Piyasa durumuna göre ek ayarlamalar
                if market_condition == 'BEARISH':
                    self.params['score_threshold_long'] += 10  # Bear piyasada long girişleri için eşiği yükselt
                elif market_condition == 'BULLISH':
                    self.params['score_threshold_short'] += 10  # Bull piyasada short girişleri için eşiği yükselt
                
                logger.info(f"Düşük performans nedeniyle strateji parametreleri ayarlandı: "
                           f"Kazanma oranı {win_rate:.2f}, SL={self.params['static_sl_percent']:.2f}%, "
                           f"Min Skor={self.params['min_score_to_trade']}")
            elif win_rate > 0.7:
                # Daha agresif ayarlar
                self.params['account_risk_per_trade'] = min(2.0, self.params['account_risk_per_trade'] * 1.1)
                
                # Kar hedeflerini optimize et
                if performance_history:
                    avg_win_pct = sum(t.get('win_pct', 0) for t in win_trades) / len(win_trades) if win_trades else 1.0
                    if avg_win_pct > 3.0:
                        # Daha yüksek kar hedefleri
                        new_tp_targets = [tp * 1.1 for tp in self.params['take_profit_targets']]
                        self.params['take_profit_targets'] = new_tp_targets
                
                # Piyasa durumuna göre ek ayarlamalar
                if market_condition == 'BEARISH':
                    self.params['score_threshold_long'] -= 5  # Daha fazla long fırsatı için eşiği biraz düşür
                elif market_condition == 'BULLISH':
                    self.params['score_threshold_short'] -= 5  # Daha fazla short fırsatı için eşiği biraz düşür
                
                logger.info(f"Yüksek performans nedeniyle strateji parametreleri ayarlandı: "
                           f"Kazanma oranı {win_rate:.2f}, Risk={self.params['account_risk_per_trade']:.2f}%")
            
            # Kaybedilen işlemlerin detaylı analizi
            if loss_trades:
                # Kısa sürede kaybedilen işlemlerde stop loss seviyelerini yükselt
                quick_losses = [t for t in loss_trades if t.get('duration_minutes', 0) < 60]
                if quick_losses and len(quick_losses) > len(loss_trades) * 0.5:
                    # %50'den fazla kayıp hızlı gerçekleşiyorsa stop loss'u artır
                    self.params['static_sl_percent'] += 0.5
                    logger.info(f"Hızlı kayıplar nedeniyle stop loss artırıldı: {self.params['static_sl_percent']:.2f}%")
            
            # Kaydedilen eski parametre değerlerinin değiştiğini kontrol et
            params_changed = any(original_params[key] != self.params[key] for key in original_params)
            
            if params_changed:
                # Değişiklikleri kaydet
                self.optimization_history.append({
                    'timestamp': now,
                    'win_rate': win_rate,
                    'market_condition': market_condition,
                    'original_params': original_params,
                    'new_params': {k: self.params[k] for k in original_params}
                })
                
                # Son optimizasyon zamanını güncelle
                self.last_optimization_time = now
                
                logger.info("Strateji parametreleri başarıyla optimize edildi")
                return True
            
            return False
        except Exception as e:
            logger.error(f"Strateji parametreleri optimize edilirken hata: {e}")
            return False
    
    def adapt_to_weekend(self, is_weekend: bool) -> bool:
        """Hafta sonu için parametreleri uyarlar."""
        if self.params.get('weekend_mode') == 'DISABLED' and is_weekend:
            logger.info("Hafta sonu modu: İşlem devre dışı")
            return False  # İşlem yapma
        
        if is_weekend and self.params.get('weekend_mode') == 'REDUCED_RISK':
            # Hafta sonu riski azalt
            self.params['account_risk_per_trade'] /= 2
            self.params['max_leverage'] = min(self.params.get('max_leverage', 10), 3)
            self.params['max_open_positions'] = max(1, self.params.get('max_open_positions', 5) // 2)
            
            logger.info(f"Hafta sonu modunda azaltılmış risk: "
                       f"Risk={self.params['account_risk_per_trade']:.2f}%, "
                       f"Max Pozisyon={self.params['max_open_positions']}, "
                       f"Max Kaldıraç={self.params['max_leverage']}")
        
        return True  # İşlem yap
    
    def adapt_to_time_of_day(self) -> bool:
        """Günün saatine göre parametreleri uyarlar."""
        now = datetime.utcnow()
        hour = now.hour
        
        if self.params.get('trading_hours_only', False):
            start_hour = self.params.get('trading_hours_start', 9)
            end_hour = self.params.get('trading_hours_end', 17)
            
            if not (start_hour <= hour < end_hour):
                logger.info(f"İşlem saati dışında: {hour} UTC")
                return False  # İşlem saatleri dışında
        
        return True  # İşlem yap
    
    def get_trading_symbols(self, all_symbols: List[str]) -> List[str]:
        """İşlem yapılacak sembolleri filtreler."""
        filtered_symbols = []
        
        # Whitelist varsa sadece onu kullan
        if any(self.params.get('whitelist_symbols', [])):
            filtered_symbols = [s for s in all_symbols if s in self.params.get('whitelist_symbols', [])]
        else:
            # Blacklist'te olmayanları al
            filtered_symbols = [s for s in all_symbols if s not in self.params.get('blacklist_symbols', [])]
        
        # Quote asset ile bitenleri filtrele
        quote_asset = self.params.get('quote_asset', 'USDT')
        filtered_symbols = [s for s in filtered_symbols if s.endswith(quote_asset)]
        
        return filtered_symbols