"""
Özel istisna sınıfları modülü
"""

class CustomError(Exception):
    """Özel hata sınıfı"""
    pass

class NetworkError(CustomError):
    """Ağ hatası durumunda kullanılır"""
    pass

class APIError(CustomError):
    """API hatası durumunda kullanılır"""
    pass

class AccountError(CustomError):
    """Hesap/Bakiye hatası durumunda kullanılır"""
    pass

class InputError(CustomError):
    """Hatalı giriş parametreleri durumunda kullanılır"""
    pass

class StrategyError(CustomError):
    """Strateji hataları durumunda kullanılır"""
    pass
