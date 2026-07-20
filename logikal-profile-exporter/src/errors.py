class LogikalAutomationError(Exception):
    """الاستثناء الأساسي لجميع أخطاء الأتمتة داخل Logikal."""
    pass

class LogikalNotRunningError(LogikalAutomationError):
    """يحدث عندما لا يمكن العثور على عملية Logikal أو تشغيلها."""
    pass

class UIControlNotFoundError(LogikalAutomationError):
    """يحدث عندما يفشل التطبيق في الإمساك بعنصر واجهة معين."""
    pass

class ExportTimeoutError(LogikalAutomationError):
    """يحدث عندما يستغرق تصدير ملف الـ DXF وقتًا أطول من المسموح."""
    pass

class InvalidDXFFileError(LogikalAutomationError):
    """يحدث عندما يتم تصدير ملف تالف أو فارغ."""
    pass