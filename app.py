import streamlit as st
import requests
import json
import logging
import base64
import io
import time
from PIL import Image
from typing import List, Optional
import uuid
import os

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация API Yes Ai
API_KEY = "yes-b091ffe8d0f341ba9b4dbf18092c0c919a16a3e117d2c9b311dbd24fc122"
API_URL_GEN_IMAGE = "https://api.yesai.su/v2/google/nanobanana/generations"
API_URL_QUERY_IMAGE = "https://api.yesai.su/v2/google/nanobanana/generations/"

# Конфигурация Freeimage.host
FREEIMAGE_API_KEY = "6d207e02198a847aa98d0a2a901485a5"
FREEIMAGE_API_URL = "https://freeimage.host/api/1/upload"

# Создаем папку для сохранения изображений
IMAGES_FOLDER = "generated_images"
os.makedirs(IMAGES_FOLDER, exist_ok=True)

class FreeImageUploader:
    """Класс для загрузки изображений на Freeimage.host"""
    
    def __init__(self):
        self.api_key = FREEIMAGE_API_KEY
        self.api_url = FREEIMAGE_API_URL
    
    def upload_image(self, image_bytes: bytes, filename: str = None) -> Optional[str]:
        """
        Загружает изображение на Freeimage.host и возвращает прямую ссылку
        """
        try:
            if not filename:
                filename = f"image_{uuid.uuid4().hex[:8]}.jpg"
            
            # Кодируем изображение в base64
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            
            # Создаем данные для POST запроса
            data = {
                'key': self.api_key,
                'action': 'upload',
                'source': base64_image,
                'format': 'json'
            }
            
            logger.info(f"Отправка изображения на Freeimage.host...")
            
            response = requests.post(self.api_url, data=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                
                # Проверяем статус ответа
                if result.get('status_code') == 200 and result.get('success', {}).get('code') == 200:
                    # Получаем прямую ссылку на изображение
                    image_url = result['image']['url']
                    logger.info(f"Изображение успешно загружено на Freeimage.host: {image_url}")
                    return image_url
                else:
                    error_msg = result.get('status_txt', 'Unknown error')
                    logger.error(f"Ошибка Freeimage.host API: {error_msg}")
                    return None
            else:
                error_text = response.text
                logger.error(f"Ошибка HTTP при загрузке на Freeimage.host: {response.status}, {error_text}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error("Таймаут при загрузке на Freeimage.host")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка подключения к Freeimage.host: {e}")
            return None
        except Exception as e:
            logger.error(f"Неожиданная ошибка при загрузке на Freeimage.host: {e}")
            return None
    
    def verify_image_url(self, url: str) -> bool:
        """Проверяет доступность URL изображения"""
        try:
            response = requests.head(url, timeout=5, allow_redirects=True)
            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', '')
                if content_type.startswith('image/'):
                    logger.info(f"URL {url} доступен и является изображением")
                    return True
                else:
                    logger.warning(f"URL {url} не является изображением: {content_type}")
            else:
                logger.warning(f"URL {url} недоступен: {response.status}")
        except Exception as e:
            logger.warning(f"Ошибка при проверке URL {url}: {e}")
        return False
    
    def verify_image_urls(self, urls: List[str]) -> List[str]:
        """Проверяет доступность нескольких URL изображений"""
        valid_urls = []
        for url in urls:
            if self.verify_image_url(url):
                valid_urls.append(url)
        return valid_urls

class ImageGenerator:
    """Класс для генерации изображений через API Yes Ai"""
    
    def __init__(self):
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        }
        self.image_uploader = FreeImageUploader()
    
    def process_image(self, image_bytes: bytes) -> Optional[dict]:
        """Обрабатывает изображение для отправки в API"""
        try:
            # Определяем тип изображения
            image = Image.open(io.BytesIO(image_bytes))
            format_str = image.format
            
            mime_types = {
                'JPEG': "image/jpeg",
                'PNG': "image/png",
                'GIF': "image/gif",
                'WEBP': "image/webp"
            }
            mime_type = mime_types.get(format_str, "image/jpeg")
            
            # Конвертируем в base64
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            
            logger.info(f"Изображение обработано: {mime_type}, размер: {len(base64_image)} символов")
            
            return {
                "data": base64_image,
                "mime_type": mime_type,
                "image_bytes": image_bytes
            }
            
        except Exception as e:
            logger.error(f"Ошибка при обработке изображения: {e}")
            return None
    
    def upload_to_freeimage(self, image_bytes: bytes, filename: str = None) -> Optional[str]:
        """Загружает изображение на Freeimage.host"""
        return self.image_uploader.upload_image(image_bytes, filename)
    
    def generate_image(self, prompt: str, customer_id: str) -> dict:
        """Генерация изображения по промпту"""
        data = {
            "version": "v.2",
            "prompt": prompt,
            "style": "0",
            "dimensions": "9:16",
            "customer_id": customer_id
        }
        
        logger.info(f"Генерация изображения для customer_id: {customer_id}, prompt: {prompt[:50]}...")
        
        try:
            response = requests.post(
                API_URL_GEN_IMAGE,
                headers=self.headers,
                json=data,
                timeout=60
            )
            
            if response.status_code != 200:
                error_text = response.text
                logger.error(f"HTTP Error: {response.status}, Response: {error_text}")
                
                if "CUSTOMER_ID_IS_EMPTY" in error_text:
                    return {"error": "CUSTOMER_ID_IS_EMPTY", "message": "Не указан ID клиента"}
                elif "CUSTOMER_ID_NOT_VALID" in error_text:
                    return {"error": "CUSTOMER_ID_NOT_VALID", "message": "Неверный формат ID клиента"}
                elif "PROMPT_IS_EMPTY" in error_text:
                    return {"error": "PROMPT_IS_EMPTY", "message": "Промпт не может быть пустым"}
                elif "PROMPT_NSFW_WORDS" in error_text:
                    return {"error": "PROMPT_NSFW_WORDS", "message": "Обнаружены запрещенные слова"}
                
                return {"error": f"HTTP {response.status}", "message": error_text}
            
            result = response.json()
            logger.info(f"Успешный ответ от API: {result}")
            return result
            
        except requests.exceptions.Timeout:
            logger.error("Таймаут при генерации изображения")
            return {"error": "timeout", "message": "Превышено время ожидания"}
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка подключения: {e}")
            return {"error": "connection_error", "message": str(e)}
        except Exception as e:
            logger.error(f"Неожиданная ошибка: {e}")
            return {"error": "unexpected_error", "message": str(e)}
    
    def generate_multi_image(self, prompt: str, references_urls: List[str], customer_id: str) -> dict:
        """
        Генерация изображения с несколькими референсами
        Поддерживается до 10 изображений
        """
        
        # Ограничиваем количество референсов (максимум 10)
        if len(references_urls) > 10:
            logger.warning(f"Слишком много референсов: {len(references_urls)}, обрезаем до 10")
            references_urls = references_urls[:10]
        
        # Проверяем доступность URL
        logger.info(f"Проверка {len(references_urls)} URL изображений...")
        valid_urls = self.image_uploader.verify_image_urls(references_urls)
        
        if not valid_urls:
            logger.error("Нет доступных URL изображений")
            return {"error": "no_valid_images", "message": "Ни одно из изображений недоступно"}
        
        if len(valid_urls) < len(references_urls):
            logger.warning(f"Доступно только {len(valid_urls)} из {len(references_urls)} изображений")
        
        # Формируем запрос
        data = {
            "version": "v.2",
            "prompt": prompt,
            "style": "0",
            "dimensions": "9:16",
            "customer_id": customer_id,
            "references_urls": valid_urls
        }
        
        logger.info(f"Multi-image генерация для customer_id: {customer_id}, референсов: {len(valid_urls)}")
        
        try:
            response = requests.post(
                API_URL_GEN_IMAGE,
                headers=self.headers,
                json=data,
                timeout=60
            )
            
            if response.status_code != 200:
                error_text = response.text
                logger.error(f"HTTP Error: {response.status}, Response: {error_text}")
                
                if "CUSTOMER_ID_IS_EMPTY" in error_text:
                    return {"error": "CUSTOMER_ID_IS_EMPTY", "message": "Не указан ID клиента"}
                elif "REFERENCES_URLS_NOT_VALID" in error_text:
                    return {"error": "REFERENCES_URLS_NOT_VALID", "message": "Неверные URL референсов"}
                elif "REFERENCES_URLS_IS_EMPTY" in error_text:
                    return {"error": "REFERENCES_URLS_IS_EMPTY", "message": "Не указаны референсы"}
                
                return {"error": f"HTTP {response.status}", "message": error_text}
            
            result = response.json()
            logger.info(f"Успешный ответ multi-image API: {result}")
            return result
            
        except requests.exceptions.Timeout:
            logger.error("Таймаут при multi-image генерации")
            return {"error": "timeout", "message": "Превышено время ожидания"}
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка подключения: {e}")
            return {"error": "connection_error", "message": str(e)}
        except Exception as e:
            logger.error(f"Неожиданная ошибка: {e}")
            return {"error": "unexpected_error", "message": str(e)}
    
    def get_task_result(self, task_id: str, max_attempts: int = 30, wait_time: int = 5) -> Optional[dict]:
        """Получает результат задачи по task_id"""
        try:
            url = f"{API_URL_QUERY_IMAGE}{task_id}"
            
            for attempt in range(max_attempts):
                time.sleep(wait_time)
                
                response = requests.get(url, headers=self.headers, timeout=30)
                
                if response.status_code != 200:
                    logger.warning(f"Попытка {attempt + 1}: статус {response.status_code}")
                    continue
                
                result = response.json()
                logger.info(f"Полный ответ API: {json.dumps(result, indent=2)}")
                
                if 'results' in result and 'generation_data' in result['results']:
                    data = result['results']['generation_data']
                    status = data.get('status')
                    result_url = data.get('result_url')
                    
                    logger.info(f"Попытка {attempt + 1}: статус={status}, result_url={result_url}")
                    
                    if status == 2:
                        if result_url:
                            return {
                                "status": "success",
                                "image_url": result_url
                            }
                        else:
                            logger.warning(f"Статус 2, но result_url пустой")
                    
                    elif status == 3:
                        error_msg = data.get('comment_ru') or data.get('comment_en') or "Ошибка генерации"
                        return {
                            "status": "failed",
                            "error": error_msg
                        }
                    
                    elif status == 4:
                        return {
                            "status": "timeout",
                            "error": "Превышено время ожидания"
                        }
                
                if attempt == max_attempts - 1:
                    return {
                        "status": "timeout",
                        "error": "Превышено максимальное количество попыток"
                    }
                    
        except Exception as e:
            logger.error(f"Ошибка при получении результата: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def download_and_save_image(self, image_url: str) -> Optional[str]:
        """Скачивает изображение по URL и сохраняет локально"""
        try:
            logger.info(f"Скачивание изображения с URL: {image_url}")
            
            # Скачиваем изображение
            response = requests.get(image_url, timeout=30)
            
            if response.status_code != 200:
                logger.error(f"Не удалось скачать изображение: {response.status_code}")
                return None
            
            # Проверяем, что это действительно изображение
            content_type = response.headers.get('Content-Type', '')
            if not content_type.startswith('image/'):
                logger.warning(f"Получен неожиданный Content-Type: {content_type}")
            
            # Генерируем уникальное имя файла
            filename = f"{uuid.uuid4()}.jpg"
            filepath = os.path.join(IMAGES_FOLDER, filename)
            
            # Сохраняем изображение
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            # Проверяем, что файл сохранен и может быть открыт
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                # Пробуем открыть изображение для проверки
                try:
                    img = Image.open(filepath)
                    img.verify()
                    logger.info(f"Изображение успешно сохранено и проверено: {filepath}")
                    return filepath
                except Exception as e:
                    logger.error(f"Сохраненный файл не является корректным изображением: {e}")
                    os.remove(filepath)
                    return None
            else:
                logger.error(f"Файл не сохранен или пустой: {filepath}")
                return None
            
        except Exception as e:
            logger.error(f"Ошибка при скачивании изображения: {e}")
            return None

def build_prompt(base_prompt: str, toggles: dict) -> str:
    """
    Строит финальный промпт на основе базового промпта и активных тумблеров
    """
    # Обновленные тексты промптов
    toggle_texts = {
        'price_tags': "проанализируй картинку, это стеллаж с товарами, посмотри где не хватает ценников под товаром, помести туда ценник, исходя из соседних ценников",
        'random_angle': "поменяй случайно ракурс фотографии, учитывай что эту фотографию делает человек и ракурс не может быть слишком высоким или слишком низким, так же учитывай что товары и ценники должны быть хорошо видны",
        'messy_shelf': "проанализируй картинку, это стеллаж с товарами, представь что в течение дня покупатели взаимодействовали с этой полкой, случайным образом убери часть товаров",
        'professional_arrangement': "проанализируй картинку, это стеллаж с товарами, представь что пришел мерчендайзер и выставил все товары, которых не хватало, добавил ценники, которых не хватало",
        'auto_fix': "проанализируй картинку, это стеллаж с товарами, сделай профессиональную выкладку товаров на полках"
    }
    
    # Собираем активные тексты
    active_texts = []
    for toggle_id, is_active in toggles.items():
        if is_active and toggle_id in toggle_texts:
            active_texts.append(toggle_texts[toggle_id])
    
    # Если нет активных тумблеров, возвращаем базовый промпт
    if not active_texts:
        return base_prompt.strip() if base_prompt else ""
    
    # Если базовый промпт пустой, возвращаем только тексты тумблеров
    if not base_prompt or not base_prompt.strip():
        return ". ".join(active_texts)
    
    # Иначе объединяем базовый промпт с текстами тумблеров
    return f"{base_prompt.strip()}. {' '.join(active_texts)}"

def process_uploaded_files(uploaded_files):
    """Обрабатывает загруженные файлы и возвращает список изображений"""
    if not uploaded_files:
        return []
    
    # Ограничиваем количество файлов
    if len(uploaded_files) > 10:
        st.warning("Можно загрузить не более 10 изображений. Первые 10 будут использованы.")
        uploaded_files = uploaded_files[:10]
    
    processed_images = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, uploaded_file in enumerate(uploaded_files):
        try:
            # Проверяем, не загружали ли мы уже этот файл
            file_key = f"{uploaded_file.name}_{uploaded_file.size}"
            
            # Если файл уже есть в session_state, пропускаем загрузку
            if 'uploaded_files_cache' not in st.session_state:
                st.session_state.uploaded_files_cache = {}
            
            if file_key in st.session_state.uploaded_files_cache:
                cached_image = st.session_state.uploaded_files_cache[file_key]
                processed_images.append(cached_image)
                status_text.text(f"✅ {uploaded_file.name} (из кэша)")
                progress_bar.progress((i + 1) / len(uploaded_files))
                continue
            
            status_text.text(f"🔄 Обработка {uploaded_file.name}...")
            
            # Читаем файл
            bytes_data = uploaded_file.getvalue()
            
            # Проверяем размер
            if len(bytes_data) > 32 * 1024 * 1024:  # 32 МБ
                st.warning(f"❌ {uploaded_file.name} превышает 32 МБ и не будет загружен")
                continue
            
            # Загружаем на Freeimage.host
            generator = ImageGenerator()
            status_text.text(f"📤 Загрузка {uploaded_file.name} на Freeimage.host...")
            image_url = generator.upload_to_freeimage(
                bytes_data, 
                f"image_{int(time.time())}_{i}.jpg"
            )
            
            if image_url:
                # Создаем превью
                image = Image.open(io.BytesIO(bytes_data))
                image.thumbnail((200, 200))
                img_byte_arr = io.BytesIO()
                image.save(img_byte_arr, format='JPEG')
                thumbnail = img_byte_arr.getvalue()
                
                image_info = {
                    "name": uploaded_file.name,
                    "thumbnail": thumbnail,
                    "url": image_url,
                    "bytes": bytes_data,
                    "file_key": file_key
                }
                
                # Сохраняем в кэш
                st.session_state.uploaded_files_cache[file_key] = image_info
                processed_images.append(image_info)
                
                status_text.text(f"✅ {uploaded_file.name} загружен")
            else:
                st.warning(f"❌ Не удалось загрузить {uploaded_file.name}")
            
            progress_bar.progress((i + 1) / len(uploaded_files))
            
        except Exception as e:
            st.error(f"Ошибка при обработке {uploaded_file.name}: {str(e)}")
    
    progress_bar.empty()
    status_text.empty()
    
    return processed_images

def main():
    """Основная функция Streamlit приложения"""
    
    # Настройка страницы
    st.set_page_config(
        page_title="Генератор изображений Yes Ai",
        page_icon="🎨",
        layout="wide"
    )
    
    # Заголовок
    st.title("🎨 Генератор изображений на базе Yes Ai")
    st.markdown("---")
    
    # Инициализация session state
    if 'generator' not in st.session_state:
        st.session_state.generator = ImageGenerator()
    
    if 'uploaded_images' not in st.session_state:
        st.session_state.uploaded_images = []
    
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    
    if 'last_result_path' not in st.session_state:
        st.session_state.last_result_path = None
    
    if 'last_result_url' not in st.session_state:
        st.session_state.last_result_url = None
    
    if 'task_id' not in st.session_state:
        st.session_state.task_id = None
    
    if 'customer_id' not in st.session_state:
        st.session_state.customer_id = str(uuid.uuid4())[:8]
    
    if 'uploaded_files_cache' not in st.session_state:
        st.session_state.uploaded_files_cache = {}
    
    if 'current_prompt' not in st.session_state:
        st.session_state.current_prompt = ""
    
    if 'toggle_states' not in st.session_state:
        st.session_state.toggle_states = {
            'price_tags': False,
            'random_angle': False,
            'messy_shelf': False,
            'professional_arrangement': False,
            'auto_fix': False
        }
    
    if 'generation_completed' not in st.session_state:
        st.session_state.generation_completed = False
    
    # Боковая панель с информацией
    with st.sidebar:
        st.header("ℹ️ Информация")
        st.markdown(f"""
        **ID клиента:** `{st.session_state.customer_id}`
        
        **Как это работает:**
        1. Загрузите до 10 изображений
        2. Напишите промпт (описание желаемого результата)
        3. Настройте параметры генерации с помощью ползунков
        4. Нажмите "Сгенерировать"
        5. Подождите 30-60 секунд
        
        **Особенности:**
        • Изображения кэшируются - не загружаются повторно
        • До 10 референсных изображений
        • Нейросеть Nano Banana 2
        • Формат: 9:16 (вертикальный)
        """)
        
        st.markdown("---")
        st.markdown("**Статус:**")
        st.info(f"📎 Загружено изображений: {len(st.session_state.uploaded_images)}/10")
        
        # Кнопка очистки кэша
        if st.button("🗑️ Очистить кэш изображений", use_container_width=True):
            try:
                # Очищаем кэш в session_state
                st.session_state.uploaded_files_cache = {}
                st.session_state.uploaded_images = []
                st.session_state.last_result_path = None
                st.session_state.last_result_url = None
                st.session_state.generation_completed = False
                
                # Удаляем файлы
                for filename in os.listdir(IMAGES_FOLDER):
                    filepath = os.path.join(IMAGES_FOLDER, filename)
                    if os.path.isfile(filepath):
                        os.remove(filepath)
                st.success("✅ Кэш очищен")
                st.rerun()
            except Exception as e:
                st.error(f"Ошибка при очистке: {e}")
        
        # Кнопка сброса ID клиента
        if st.button("🔄 Новый ID клиента", use_container_width=True):
            st.session_state.customer_id = str(uuid.uuid4())[:8]
            st.rerun()
    
    # Основная область
    col1, col2 = st.columns([3, 2])
    
    with col1:
        st.subheader("📤 Загрузка изображений (до 10 шт.)")
        
        # Загрузка файлов
        uploaded_files = st.file_uploader(
            "Выберите изображения",
            type=['png', 'jpg', 'jpeg', 'gif', 'webp'],
            accept_multiple_files=True,
            key="file_uploader",
            disabled=st.session_state.processing
        )
        
        # Обработка загруженных файлов (только если есть новые файлы)
        if uploaded_files and not st.session_state.processing:
            # Проверяем, изменились ли файлы
            current_files_key = str([(f.name, f.size) for f in uploaded_files])
            
            if 'last_files_key' not in st.session_state or st.session_state.last_files_key != current_files_key:
                st.session_state.last_files_key = current_files_key
                st.session_state.uploaded_images = process_uploaded_files(uploaded_files)
                # Сбрасываем результат при загрузке новых изображений
                st.session_state.last_result_path = None
                st.session_state.last_result_url = None
                st.session_state.generation_completed = False
                
                if st.session_state.uploaded_images:
                    st.success(f"✅ Успешно загружено {len(st.session_state.uploaded_images)} изображений")
        
        # Отображение загруженных изображений
        if st.session_state.uploaded_images:
            st.subheader("🖼️ Загруженные изображения")
            
            # Создаем сетку для превью
            cols_per_row = 5
            rows = (len(st.session_state.uploaded_images) + cols_per_row - 1) // cols_per_row
            
            for row in range(rows):
                cols = st.columns(cols_per_row)
                for col_idx in range(cols_per_row):
                    img_idx = row * cols_per_row + col_idx
                    if img_idx < len(st.session_state.uploaded_images):
                        img_data = st.session_state.uploaded_images[img_idx]
                        with cols[col_idx]:
                            st.image(
                                img_data["thumbnail"],
                                caption=f"{img_idx + 1}. {img_data['name'][:10]}...",
                                use_column_width=True
                            )
                            st.caption(f"✅ Загружено")
            
            # Кнопка очистки
            if st.button("🗑️ Очистить все изображения", disabled=st.session_state.processing):
                st.session_state.uploaded_images = []
                st.session_state.uploaded_files_cache = {}
                st.session_state.last_result_path = None
                st.session_state.last_result_url = None
                st.session_state.generation_completed = False
                st.rerun()
    
    with col2:
        st.subheader("📝 Промпт и настройки")
        
        # Поле для ввода промпта
        base_prompt = st.text_area(
            "Введите базовое описание (необязательно):",
            value=st.session_state.current_prompt,
            height=80,
            placeholder="Например: фотография полки с продуктами... (можно оставить пустым)",
            disabled=st.session_state.processing or len(st.session_state.uploaded_images) == 0,
            key="base_prompt_input"
        )
        
        # Обновляем промпт в session state
        if base_prompt != st.session_state.current_prompt:
            st.session_state.current_prompt = base_prompt
        
        st.markdown("### 🎛️ Настройки генерации")
        st.markdown("*Включите нужные опции для модификации промпта*")
        
        # Создаем колонки для ползунков
        toggle_col1, toggle_col2 = st.columns(2)
        
        with toggle_col1:
            price_tags = st.toggle(
                "🏷️ Добавить ценники", 
                value=st.session_state.toggle_states['price_tags'],
                key="toggle_price_tags",
                help="Анализирует где не хватает ценников и добавляет их"
            )
            
            random_angle = st.toggle(
                "🔄 Случайный ракурс", 
                value=st.session_state.toggle_states['random_angle'],
                key="toggle_random_angle",
                help="Меняет ракурс фотографии (естественный, человеческий)"
            )
            
            messy_shelf = st.toggle(
                "📦 Неопрятная полка", 
                value=st.session_state.toggle_states['messy_shelf'],
                key="toggle_messy_shelf",
                help="Имитирует взаимодействие покупателей - часть товаров убрана"
            )
        
        with toggle_col2:
            professional_arrangement = st.toggle(
                "✨ Профессиональная выкладка", 
                value=st.session_state.toggle_states['professional_arrangement'],
                key="toggle_professional",
                help="Мерчендайзер выставил все товары и добавил ценники"
            )
            
            auto_fix = st.toggle(
                "🔧 Автоисправление", 
                value=st.session_state.toggle_states['auto_fix'],
                key="toggle_autofix",
                help="Делает профессиональную выкладку товаров"
            )
        
        # Обновляем состояния тумблеров в session state
        st.session_state.toggle_states = {
            'price_tags': price_tags,
            'random_angle': random_angle,
            'messy_shelf': messy_shelf,
            'professional_arrangement': professional_arrangement,
            'auto_fix': auto_fix
        }
        
        st.markdown("---")
        
        # Строим финальный промпт
        final_prompt = build_prompt(st.session_state.current_prompt, st.session_state.toggle_states)
        
        # Отображаем финальный промпт
        if final_prompt:
            with st.expander("📝 Финальный промпт", expanded=False):
                st.write(final_prompt)
        else:
            st.warning("⚠️ Промпт пуст. Будут использованы только настройки.")
        
        # Кнопка генерации
        generate_button = st.button(
            "🚀 Сгенерировать",
            type="primary",
            use_container_width=True,
            disabled=(
                st.session_state.processing or 
                len(st.session_state.uploaded_images) == 0
            )
        )
        
        # Область для результата и статуса
        result_placeholder = st.empty()
        status_placeholder = st.empty()
        
        # Обработка генерации
        if generate_button and not st.session_state.processing:
            st.session_state.processing = True
            st.session_state.task_id = None
            st.session_state.generation_completed = False
            
            # Очищаем предыдущие результаты
            status_placeholder.empty()
            result_placeholder.empty()
            
            try:
                # Извлекаем URL изображений
                references_urls = [img["url"] for img in st.session_state.uploaded_images if "url" in img]
                
                if not references_urls:
                    st.error("❌ Нет доступных URL изображений")
                    st.session_state.processing = False
                    return
                
                # Показываем прогресс
                with status_placeholder.container():
                    status_text = st.empty()
                    status_text.info(f"🔄 Отправка запроса в API Yes Ai...")
                
                # Отправляем запрос на генерацию
                gen_result = st.session_state.generator.generate_multi_image(
                    final_prompt, 
                    references_urls, 
                    st.session_state.customer_id
                )
                
                if gen_result and "error" not in gen_result:
                    if 'results' in gen_result and 'generation_data' in gen_result['results']:
                        api_task_id = gen_result['results']['generation_data']['id']
                        st.session_state.task_id = api_task_id
                        
                        with status_placeholder.container():
                            progress_text = st.empty()
                            progress_text.info(f"🆔 ID задачи: `{api_task_id}`\n\n⏳ Ожидание результата... Это может занять 30-60 секунд")
                        
                        # Получаем результат
                        task_result = st.session_state.generator.get_task_result(api_task_id, max_attempts=30, wait_time=5)
                        
                        if task_result:
                            logger.info(f"Результат задачи: {task_result}")
                            
                            if task_result.get("status") == "success":
                                image_url = task_result.get("image_url")
                                
                                if image_url:
                                    st.session_state.last_result_url = image_url
                                    
                                    # Скачиваем и сохраняем изображение локально
                                    with status_placeholder.container():
                                        status_text.info(f"📥 Скачивание изображения...")
                                    
                                    local_path = st.session_state.generator.download_and_save_image(image_url)
                                    
                                    if local_path:
                                        st.session_state.last_result_path = local_path
                                        st.session_state.generation_completed = True
                                        
                                        # Очищаем статус
                                        status_placeholder.empty()
                                        
                                        # Отображаем результат
                                        with result_placeholder.container():
                                            st.success("✅ Генерация завершена!")
                                            st.image(local_path, caption="Результат", use_column_width=True)
                                            
                                            # Кнопка для скачивания
                                            with open(local_path, "rb") as file:
                                                st.download_button(
                                                    label="📥 Скачать изображение",
                                                    data=file,
                                                    file_name=f"generated_{uuid.uuid4()}.jpg",
                                                    mime="image/jpeg",
                                                    use_container_width=True
                                                )
                                            
                                            st.caption(f"🆔 ID задачи: {api_task_id}")
                                            st.caption(f"🔗 URL: {image_url}")
                                        
                                        # Сбрасываем флаг processing после успешного завершения
                                        st.session_state.processing = False
                                    else:
                                        st.error("❌ Не удалось сохранить изображение локально")
                                        st.session_state.processing = False
                                else:
                                    st.error("❌ Не получен URL изображения")
                                    st.session_state.processing = False
                            else:
                                error_msg = task_result.get("error", "Неизвестная ошибка")
                                st.error(f"❌ Ошибка генерации: {error_msg}")
                                st.session_state.processing = False
                        else:
                            st.error("❌ Не удалось получить результат генерации")
                            st.session_state.processing = False
                    else:
                        st.error(f"❌ Ошибка API: {gen_result}")
                        st.session_state.processing = False
                else:
                    error_msg = gen_result.get("message", gen_result.get("error", "Неизвестная ошибка")) if gen_result else "Ошибка подключения"
                    st.error(f"❌ Ошибка при генерации: {error_msg}")
                    st.session_state.processing = False
                
            except Exception as e:
                st.error(f"❌ Произошла ошибка: {str(e)}")
                logger.error(f"Ошибка генерации: {e}", exc_info=True)
                st.session_state.processing = False
            
            finally:
                # Если generation_completed уже True, processing уже сброшен
                if not st.session_state.generation_completed:
                    st.session_state.processing = False
                # Не вызываем st.rerun() здесь, чтобы избежать цикла
        
        # Если генерация завершена и есть результат, показываем его
        if st.session_state.generation_completed and st.session_state.last_result_path:
            if os.path.exists(st.session_state.last_result_path):
                with result_placeholder.container():
                    st.subheader("🎨 Последний результат")
                    st.image(st.session_state.last_result_path, caption="Результат", use_column_width=True)
                    
                    with open(st.session_state.last_result_path, "rb") as file:
                        st.download_button(
                            label="📥 Скачать изображение",
                            data=file,
                            file_name=f"generated_{uuid.uuid4()}.jpg",
                            mime="image/jpeg",
                            use_container_width=True
                        )
                    
                    if st.session_state.task_id:
                        st.caption(f"🆔 ID задачи: {st.session_state.task_id}")
                    
                    if st.session_state.last_result_url:
                        st.caption(f"🔗 URL: {st.session_state.last_result_url}")

if __name__ == "__main__":
    main()
