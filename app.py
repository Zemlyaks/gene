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
from datetime import datetime

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

# Файл для сохранения состояния (на случай обновления страницы)
STATE_FILE = "app_state.json"

def save_state_to_file():
    """Сохраняет важные состояния в файл"""
    try:
        state = {
            'customer_id': st.session_state.get('customer_id', ''),
            'last_result_path': st.session_state.get('last_result_path', ''),
            'last_result_url': st.session_state.get('last_result_url', ''),
            'task_id': st.session_state.get('task_id', ''),
            'generation_completed': st.session_state.get('generation_completed', False),
            'toggle_states': st.session_state.get('toggle_states', {}),
            'current_prompt': st.session_state.get('current_prompt', ''),
            'timestamp': datetime.now().isoformat()
        }
        
        # Сохраняем только если есть результат
        if state['last_result_path'] or state['task_id']:
            with open(STATE_FILE, 'w') as f:
                json.dump(state, f)
            logger.info(f"Состояние сохранено в файл")
    except Exception as e:
        logger.error(f"Ошибка при сохранении состояния: {e}")

def load_state_from_file():
    """Загружает состояние из файла"""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
            
            # Проверяем, не устарело ли состояние (больше 1 часа)
            timestamp = datetime.fromisoformat(state.get('timestamp', '2000-01-01'))
            if (datetime.now() - timestamp).seconds < 3600:  # 1 час
                logger.info(f"Состояние загружено из файла")
                return state
            else:
                logger.info(f"Состояние устарело, удаляем файл")
                os.remove(STATE_FILE)
    except Exception as e:
        logger.error(f"Ошибка при загрузке состояния: {e}")
    return None

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
            
            # Проверяем размер для мобильных устройств
            if len(image_bytes) > 10 * 1024 * 1024:  # 10 МБ для мобильных
                logger.warning(f"Изображение большое ({len(image_bytes)/1024/1024:.1f} МБ), может не загрузиться на мобильных")
            
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
            
            # Увеличиваем таймаут для мобильных
            response = requests.post(self.api_url, data=data, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get('status_code') == 200 and result.get('success', {}).get('code') == 200:
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
            # Увеличиваем таймаут для мобильных
            response = requests.head(url, timeout=10, allow_redirects=True)
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
            image = Image.open(io.BytesIO(image_bytes))
            format_str = image.format
            
            mime_types = {
                'JPEG': "image/jpeg",
                'PNG': "image/png",
                'GIF': "image/gif",
                'WEBP': "image/webp"
            }
            mime_type = mime_types.get(format_str, "image/jpeg")
            
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
    
    def generate_multi_image(self, prompt: str, references_urls: List[str], customer_id: str) -> dict:
        """Генерация изображения с несколькими референсами"""
        
        if len(references_urls) > 10:
            logger.warning(f"Слишком много референсов: {len(references_urls)}, обрезаем до 10")
            references_urls = references_urls[:10]
        
        logger.info(f"Проверка {len(references_urls)} URL изображений...")
        valid_urls = self.image_uploader.verify_image_urls(references_urls)
        
        if not valid_urls:
            logger.error("Нет доступных URL изображений")
            return {"error": "no_valid_images", "message": "Ни одно из изображений недоступно"}
        
        if len(valid_urls) < len(references_urls):
            logger.warning(f"Доступно только {len(valid_urls)} из {len(references_urls)} изображений")
        
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
            # Увеличиваем таймаут для мобильных
            response = requests.post(
                API_URL_GEN_IMAGE,
                headers=self.headers,
                json=data,
                timeout=120
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
                # Увеличиваем время ожидания для мобильных
                time.sleep(wait_time)
                
                try:
                    response = requests.get(url, headers=self.headers, timeout=45)
                except requests.exceptions.Timeout:
                    logger.warning(f"Попытка {attempt + 1}: таймаут, продолжаем...")
                    continue
                
                if response.status_code != 200:
                    logger.warning(f"Попытка {attempt + 1}: статус {response.status_code}")
                    continue
                
                result = response.json()
                
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
            
            # Увеличиваем таймаут для мобильных
            response = requests.get(image_url, timeout=60)
            
            if response.status_code != 200:
                logger.error(f"Не удалось скачать изображение: {response.status_code}")
                return None
            
            content_type = response.headers.get('Content-Type', '')
            if not content_type.startswith('image/'):
                logger.warning(f"Получен неожиданный Content-Type: {content_type}")
            
            filename = f"{uuid.uuid4()}.jpg"
            filepath = os.path.join(IMAGES_FOLDER, filename)
            
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
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
    """Строит финальный промпт"""
    toggle_texts = {
        'price_tags': "add price tags to all products",
        'random_angle': "поменять случайно ракурс",
        'messy_shelf': "make shelf look messy after shopping",
        'professional_arrangement': "make shelf look professionally arranged",
        'auto_fix': "make shelf look professionally arranged"
    }
    
    active_texts = []
    for toggle_id, is_active in toggles.items():
        if is_active and toggle_id in toggle_texts:
            active_texts.append(toggle_texts[toggle_id])
    
    if not active_texts:
        return base_prompt.strip() if base_prompt else ""
    
    if not base_prompt or not base_prompt.strip():
        return ", ".join(active_texts)
    
    return f"{base_prompt.strip()}, {', '.join(active_texts)}"

def process_uploaded_files(uploaded_files):
    """Обрабатывает загруженные файлы"""
    if not uploaded_files:
        return []
    
    if len(uploaded_files) > 10:
        st.warning("Можно загрузить не более 10 изображений. Первые 10 будут использованы.")
        uploaded_files = uploaded_files[:10]
    
    processed_images = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, uploaded_file in enumerate(uploaded_files):
        try:
            file_key = f"{uploaded_file.name}_{uploaded_file.size}"
            
            if 'uploaded_files_cache' not in st.session_state:
                st.session_state.uploaded_files_cache = {}
            
            if file_key in st.session_state.uploaded_files_cache:
                cached_image = st.session_state.uploaded_files_cache[file_key]
                processed_images.append(cached_image)
                status_text.text(f"✅ {uploaded_file.name} (из кэша)")
                progress_bar.progress((i + 1) / len(uploaded_files))
                continue
            
            status_text.text(f"🔄 Обработка {uploaded_file.name}...")
            
            bytes_data = uploaded_file.getvalue()
            
            # Для мобильных - предупреждение о больших файлах
            if len(bytes_data) > 10 * 1024 * 1024:
                st.warning(f"⚠️ {uploaded_file.name} большой ({len(bytes_data)/1024/1024:.1f} МБ). На мобильных может загружаться долго.")
            
            if len(bytes_data) > 32 * 1024 * 1024:
                st.warning(f"❌ {uploaded_file.name} превышает 32 МБ и не будет загружен")
                continue
            
            generator = ImageGenerator()
            status_text.text(f"📤 Загрузка {uploaded_file.name} на Freeimage.host...")
            image_url = generator.upload_to_freeimage(
                bytes_data, 
                f"image_{int(time.time())}_{i}.jpg"
            )
            
            if image_url:
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

def check_mobile_device():
    """Проверяет, запущено ли приложение на мобильном устройстве"""
    try:
        if st._is_running_with_streamlit:
            # Проверяем user agent через JavaScript
            mobile_js = """
            <script>
            const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
            if (isMobile) {
                document.body.classList.add('mobile-device');
            }
            </script>
            """
            st.components.v1.html(mobile_js, height=0)
    except:
        pass
    return False

def main():
    """Основная функция Streamlit приложения"""
    
    st.set_page_config(
        page_title="Генератор изображений Yes Ai",
        page_icon="🎨",
        layout="wide",
        initial_sidebar_state="auto"  # Адаптируется под мобильные
    )
    
    # Проверяем мобильное устройство
    check_mobile_device()
    
    st.title("🎨 Генератор изображений на базе Yes Ai")
    st.markdown("---")
    
    # Загружаем сохраненное состояние
    saved_state = load_state_from_file()
    
    # Инициализация session state
    if 'generator' not in st.session_state:
        st.session_state.generator = ImageGenerator()
    
    if 'uploaded_images' not in st.session_state:
        st.session_state.uploaded_images = []
    
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    
    if 'last_result_path' not in st.session_state:
        if saved_state and saved_state.get('last_result_path'):
            if os.path.exists(saved_state['last_result_path']):
                st.session_state.last_result_path = saved_state['last_result_path']
            else:
                st.session_state.last_result_path = None
        else:
            st.session_state.last_result_path = None
    
    if 'last_result_url' not in st.session_state:
        st.session_state.last_result_url = saved_state.get('last_result_url') if saved_state else None
    
    if 'task_id' not in st.session_state:
        st.session_state.task_id = saved_state.get('task_id') if saved_state else None
    
    if 'customer_id' not in st.session_state:
        st.session_state.customer_id = saved_state.get('customer_id', str(uuid.uuid4())[:8]) if saved_state else str(uuid.uuid4())[:8]
    
    if 'uploaded_files_cache' not in st.session_state:
        st.session_state.uploaded_files_cache = {}
    
    if 'current_prompt' not in st.session_state:
        st.session_state.current_prompt = saved_state.get('current_prompt', '') if saved_state else ''
    
    if 'toggle_states' not in st.session_state:
        st.session_state.toggle_states = saved_state.get('toggle_states', {
            'price_tags': False,
            'random_angle': False,
            'messy_shelf': False,
            'professional_arrangement': False,
            'auto_fix': False
        }) if saved_state else {
            'price_tags': False,
            'random_angle': False,
            'messy_shelf': False,
            'professional_arrangement': False,
            'auto_fix': False
        }
    
    if 'generation_completed' not in st.session_state:
        st.session_state.generation_completed = saved_state.get('generation_completed', False) if saved_state else False
    
    # Боковая панель с информацией
    with st.sidebar:
        st.header("ℹ️ Информация")
        
        # Предупреждение для мобильных
        st.markdown("""
        <style>
        .mobile-warning {
            background-color: #fff3cd;
            color: #856404;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 10px;
            font-size: 14px;
        }
        </style>
        """, unsafe_allow_html=True)
        
        st.markdown('<div class="mobile-warning">📱 Если вы на мобильном устройстве, процесс может быть медленнее. Пожалуйста, не закрывайте приложение.</div>', unsafe_allow_html=True)
        
        st.markdown(f"""
        **ID клиента:** `{st.session_state.customer_id}`
        
        **Как это работает:**
        1. Загрузите до 10 изображений
        2. Напишите промпт
        3. Настройте параметры
        4. Нажмите "Сгенерировать"
        5. Подождите 30-60 секунд
        
        **Статус:** 📎 {len(st.session_state.uploaded_images)}/10 изображений
        """)
        
        # Кнопка восстановления последнего результата
        if st.session_state.last_result_path and os.path.exists(st.session_state.last_result_path):
            if st.button("🔄 Показать последний результат", use_container_width=True):
                st.session_state.generation_completed = True
                st.rerun()
        
        # Кнопка очистки
        if st.button("🗑️ Очистить всё", use_container_width=True):
            st.session_state.uploaded_files_cache = {}
            st.session_state.uploaded_images = []
            st.session_state.last_result_path = None
            st.session_state.last_result_url = None
            st.session_state.generation_completed = False
            if os.path.exists(STATE_FILE):
                os.remove(STATE_FILE)
            for filename in os.listdir(IMAGES_FOLDER):
                filepath = os.path.join(IMAGES_FOLDER, filename)
                if os.path.isfile(filepath):
                    os.remove(filepath)
            st.success("✅ Всё очищено")
            st.rerun()
    
    # Основная область
    col1, col2 = st.columns([3, 2])
    
    with col1:
        st.subheader("📤 Загрузка изображений")
        
        uploaded_files = st.file_uploader(
            "Выберите изображения",
            type=['png', 'jpg', 'jpeg', 'gif', 'webp'],
            accept_multiple_files=True,
            key="file_uploader",
            disabled=st.session_state.processing
        )
        
        if uploaded_files and not st.session_state.processing:
            current_files_key = str([(f.name, f.size) for f in uploaded_files])
            
            if 'last_files_key' not in st.session_state or st.session_state.last_files_key != current_files_key:
                st.session_state.last_files_key = current_files_key
                st.session_state.uploaded_images = process_uploaded_files(uploaded_files)
                st.session_state.last_result_path = None
                st.session_state.last_result_url = None
                st.session_state.generation_completed = False
                
                if st.session_state.uploaded_images:
                    st.success(f"✅ Загружено {len(st.session_state.uploaded_images)} изображений")
        
        if st.session_state.uploaded_images:
            st.subheader("🖼️ Превью")
            
            # Адаптивная сетка для мобильных
            cols_per_row = 3 if check_mobile_device() else 5
            rows = (len(st.session_state.uploaded_images) + cols_per_row - 1) // cols_per_row
            
            for row in range(rows):
                cols = st.columns(cols_per_row)
                for col_idx in range(cols_per_row):
                    img_idx = row * cols_per_row + col_idx
                    if img_idx < len(st.session_state.uploaded_images):
                        img_data = st.session_state.uploaded_images[img_idx]
                        with cols[col_idx]:
                            st.image(img_data["thumbnail"], use_column_width=True)
                            st.caption(f"{img_idx + 1}")
    
    with col2:
        st.subheader("📝 Промпт и настройки")
        
        base_prompt = st.text_area(
            "Описание (необязательно):",
            value=st.session_state.current_prompt,
            height=80,
            placeholder="Например: полка с продуктами...",
            disabled=st.session_state.processing or len(st.session_state.uploaded_images) == 0,
            key="base_prompt_input"
        )
        
        if base_prompt != st.session_state.current_prompt:
            st.session_state.current_prompt = base_prompt
        
        st.markdown("### 🎛️ Настройки")
        
        toggle_col1, toggle_col2 = st.columns(2)
        
        with toggle_col1:
            price_tags = st.toggle(
                "🏷️ Ценники", 
                value=st.session_state.toggle_states['price_tags'],
                key="toggle_price_tags"
            )
            random_angle = st.toggle(
                "🔄 Случ. ракурс", 
                value=st.session_state.toggle_states['random_angle'],
                key="toggle_random_angle"
            )
            messy_shelf = st.toggle(
                "📦 Неопрятно", 
                value=st.session_state.toggle_states['messy_shelf'],
                key="toggle_messy_shelf"
            )
        
        with toggle_col2:
            professional = st.toggle(
                "✨ Профессионально", 
                value=st.session_state.toggle_states['professional_arrangement'],
                key="toggle_professional"
            )
            auto_fix = st.toggle(
                "🔧 Авто", 
                value=st.session_state.toggle_states['auto_fix'],
                key="toggle_autofix"
            )
        
        st.session_state.toggle_states = {
            'price_tags': price_tags,
            'random_angle': random_angle,
            'messy_shelf': messy_shelf,
            'professional_arrangement': professional,
            'auto_fix': auto_fix
        }
        
        final_prompt = build_prompt(st.session_state.current_prompt, st.session_state.toggle_states)
        
        if final_prompt:
            st.info(f"📝 **Промпт:** {final_prompt[:100]}{'...' if len(final_prompt) > 100 else ''}")
        
        # Кнопка генерации
        generate_button = st.button(
            "🚀 Сгенерировать",
            type="primary",
            use_container_width=True,
            disabled=st.session_state.processing or len(st.session_state.uploaded_images) == 0
        )
        
        # Области для результатов
        result_placeholder = st.empty()
        status_placeholder = st.empty()
        
        # Обработка генерации
        if generate_button and not st.session_state.processing:
            st.session_state.processing = True
            st.session_state.task_id = None
            st.session_state.generation_completed = False
            
            try:
                references_urls = [img["url"] for img in st.session_state.uploaded_images if "url" in img]
                
                if not references_urls:
                    st.error("❌ Нет URL изображений")
                    st.session_state.processing = False
                    return
                
                with status_placeholder.container():
                    status_text = st.empty()
                    status_text.info(f"🔄 Отправка запроса...")
                
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
                            progress_text.info(f"🆔 ID: {api_task_id}\n\n⏳ Ожидание... 30-60 сек")
                        
                        task_result = st.session_state.generator.get_task_result(api_task_id, max_attempts=30, wait_time=5)
                        
                        if task_result:
                            if task_result.get("status") == "success":
                                image_url = task_result.get("image_url")
                                
                                if image_url:
                                    st.session_state.last_result_url = image_url
                                    
                                    with status_placeholder.container():
                                        status_text.info(f"📥 Скачивание...")
                                    
                                    local_path = st.session_state.generator.download_and_save_image(image_url)
                                    
                                    if local_path:
                                        st.session_state.last_result_path = local_path
                                        st.session_state.generation_completed = True
                                        
                                        # Сохраняем состояние
                                        save_state_to_file()
                                        
                                        status_placeholder.empty()
                                        
                                        with result_placeholder.container():
                                            st.success("✅ Готово!")
                                            st.image(local_path, use_column_width=True)
                                            
                                            with open(local_path, "rb") as file:
                                                st.download_button(
                                                    label="📥 Скачать",
                                                    data=file,
                                                    file_name=f"generated.jpg",
                                                    mime="image/jpeg",
                                                    use_container_width=True
                                                )
                                    else:
                                        st.error("❌ Ошибка сохранения")
                                else:
                                    st.error("❌ Нет URL")
                            else:
                                st.error(f"❌ Ошибка: {task_result.get('error', 'Неизвестно')}")
                        else:
                            st.error("❌ Нет результата")
                    else:
                        st.error(f"❌ Ошибка API")
                else:
                    error_msg = gen_result.get("message", "Неизвестная ошибка") if gen_result else "Ошибка"
                    st.error(f"❌ {error_msg}")
                
            except Exception as e:
                st.error(f"❌ Ошибка: {str(e)}")
                logger.error(f"Ошибка: {e}", exc_info=True)
            
            finally:
                st.session_state.processing = False
                st.rerun()
        
        # Показываем последний результат
        elif st.session_state.generation_completed and st.session_state.last_result_path:
            if os.path.exists(st.session_state.last_result_path):
                with result_placeholder.container():
                    st.subheader("🎨 Результат")
                    st.image(st.session_state.last_result_path, use_column_width=True)
                    
                    with open(st.session_state.last_result_path, "rb") as file:
                        st.download_button(
                            label="📥 Скачать",
                            data=file,
                            file_name=f"generated.jpg",
                            mime="image/jpeg",
                            use_container_width=True
                        )

if __name__ == "__main__":
    main()
