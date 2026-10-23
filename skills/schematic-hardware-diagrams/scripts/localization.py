"""Localize renderer UI; circuit-specific prose is supplied by the agent."""
import re
import unicodedata

LEGENDS = {
    'en': ('Data / status', 'Control / configuration', 'Power', 'Reference'),
    'zh-Hans': ('数据 / 状态', '控制 / 配置', '供电', '基准'),
    'zh-Hant': ('資料 / 狀態', '控制 / 設定', '供電', '基準'),
    'ja': ('データ / 状態', '制御 / 設定', '電源', '基準'),
    'ko': ('데이터 / 상태', '제어 / 설정', '전원', '기준'),
    'de': ('Daten / Status', 'Steuerung / Konfiguration', 'Versorgung', 'Referenz'),
    'fr': ('Données / état', 'Commande / configuration', 'Alimentation', 'Référence'),
    'es': ('Datos / estado', 'Control / configuración', 'Alimentación', 'Referencia'),
    'pt': ('Dados / estado', 'Controle / configuração', 'Alimentação', 'Referência'),
    'it': ('Dati / stato', 'Controllo / configurazione', 'Alimentazione', 'Riferimento'),
    'ru': ('Данные / состояние', 'Управление / настройка', 'Питание', 'Опорный сигнал'),
    'ar': ('البيانات والحالة', 'التحكم والإعداد', 'الطاقة', 'المرجع'),
    'he': ('נתונים ומצב', 'בקרה והגדרות', 'הספק', 'ייחוס'),
}
KEYS = ('data', 'control', 'power', 'reference')

def normalize_locale(value):
    value = (value or 'en').replace('_', '-')
    lower = value.lower()
    if lower in ('zh-tw', 'zh-hk', 'zh-mo') or lower.startswith('zh-hant'):
        return 'zh-Hant'
    if lower == 'zh' or lower.startswith(('zh-cn', 'zh-sg', 'zh-hans')):
        return 'zh-Hans'
    return value.split('-')[0].lower()

def detect_locale(prompt):
    """Heuristic for unambiguous prompts; explicit output instructions are agent-resolved."""
    cleaned = re.sub(r'`[^`]*`|https?://\S+|\b[A-Z][A-Z0-9_./-]{2,}\b', ' ', prompt)
    if re.search(r'[\u3040-\u30ff]', cleaned): return 'ja'
    if re.search(r'[\uac00-\ud7af]', cleaned): return 'ko'
    if re.search(r'[\u4e00-\u9fff]', cleaned):
        return 'zh-Hant' if re.search(r'[圖輸電號體傳設與顯實態數參線頁這個請]', cleaned) else 'zh-Hans'
    if re.search(r'[\u0590-\u05ff]', cleaned): return 'he'
    if re.search(r'[\u0600-\u06ff]', cleaned): return 'ar'
    if re.search(r'[\u0400-\u04ff]', cleaned): return 'ru'
    words = set(re.findall(r'[^\W\d_]+', cleaned.casefold(), re.UNICODE))
    clues = {
        'de': {'erstelle','schaltplan','schaltung','hardwareübersicht','blockdiagramm','und','diesem','bitte'},
        'fr': {'analysez','schéma','créez','matériel','chaque','avec','circuit','veuillez'},
        'es': {'analiza','esquema','crea','diagrama','módulos','este','por','favor'},
        'pt': {'analise','esquemático','crie','módulos','este','por','favor','elétrico'},
        'it': {'analizza','schema','crea','moduli','questo','per','favore'},
    }
    scores = {locale: len(words & values) for locale, values in clues.items()}
    winner = max(scores, key=scores.get)
    return winner if scores[winner] >= 2 else 'en'

def get_legend(locale, override=None):
    if override is not None:
        if set(override) != set(KEYS) or not all(isinstance(override[k], str) and override[k].strip() for k in KEYS):
            raise ValueError('legend must provide nonempty data/control/power/reference strings')
        return override
    locale = normalize_locale(locale)
    if locale not in LEGENDS:
        raise ValueError(f'Locale {locale!r} needs a translated legend object')
    return dict(zip(KEYS, LEGENDS[locale]))

def needs_shaping(text):
    return any((0x0590 <= ord(c) <= 0x08ff or 0x0900 <= ord(c) <= 0x0eff) and unicodedata.category(c).startswith('L') for c in text)

def is_rtl(text):
    return any(unicodedata.bidirectional(c) in ('R', 'AL') for c in text)
