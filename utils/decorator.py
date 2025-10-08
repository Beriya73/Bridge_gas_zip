import time
from functools import wraps
from loguru import logger

def retry(max_attempts=3, delay=1):
    """Декоратор для повторных запросов.
    Args:
        max_attempts: Максимальное количество попыток (по умолчанию: 3).
        delay: Задержка между попытками в секундах (по умолчанию: 1).
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    logger.warning(f"Попытка {attempt}/{max_attempts} завершилась с ошибкой: {e}")
                    if attempt < max_attempts:
                        time.sleep(delay * attempt)
            logger.error(f"Все {max_attempts} попыток исчерпаны. Последняя ошибка: {last_error}")
            return None
        return wrapper
    return decorator
