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

# Файл для сохранения состояния
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
            
            timestamp = datetime.fromisoformat(state.get('timestamp', '2000-01-01'))
            if (datetime.now() - timestamp).seconds < 3600:
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
        """Загружает изображение на Freeimage.host"""
        try:
            if not filename:
                filename = f"image_{uuid.uuid4().hex[:8]}.jpg"
            
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            
            data = {
                'key': self.api_key,
                'action': 'upload',
                'source': base64_image,
                'format': 'json'
            }
            
            logger.info(f"Отправка изображения на Freeimage.host...")
            response = requests.post(self.api_url, data=data, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status_code') == 200 and result.get('success', {}).get('code') == 200:
                    image_url = result['image']['url']
                    logger.info(f"Изображение успешно загружено: {image_url}")
                    return image_url
            return None
        except Exception as e:
            logger.error(f"Ошибка при загрузке: {e}")
            return None
    
    def verify_image_url(self, url: str) -> bool:
        """Проверяет доступность URL изображения"""
        try:
            response = requests.head(url, timeout=10, allow_redirects=True)
            return response.status_code == 200
        except:
            return False
    
    def verify_image_urls(self, urls: List[str]) -> List[str]:
        """Проверяет доступность нескольких URL"""
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
    
    def upload_to_freeimage(self, image_bytes: bytes, filename: str = None) -> Optional[str]:
        """Загружает изображение на Freeimage.host"""
        return self.image_uploader.upload_image(image_bytes, filename)
    
    def generate_multi_image(self, prompt: str, references_urls: List[str], customer_id: str) -> dict:
        """Генерация изображения с несколькими референсами"""
        
        if len(references_urls) > 10:
            references_urls = references_urls[:10]
        
        valid_urls = self.image_uploader.verify_image_urls(references_urls)
        
        if not valid_urls:
            return {"error": "no_valid_images", "message": "Ни одно из изображений недоступно"}
        
        data = {
            "version": "v.2",
            "prompt": prompt,
            "style": "0",
            "dimensions": "9:16",
            "customer_id": customer_id,
            "references_urls": valid_urls
        }
        
        try:
            response = requests.post(API_URL_GEN_IMAGE, headers=self.headers, json=data, timeout=120)
            
            if response.status_code != 200:
                return {"error": f"HTTP {response.status}", "message": response.text}
            
            return response.json()
            
        except Exception as e:
            return {"error": str(e)}
    
    def get_task_result(self, task_id: str, max_attempts: int = 60, wait_time: int = 5) -> Optional[dict]:
        """Получает результат задачи по task_id с увеличенным количеством попыток"""
        try:
            url = f"{API_URL_QUERY_IMAGE}{task_id}"
            
            for attempt in range(max_attempts):
                time.sleep(wait_time)
                
                try:
                    response = requests.get(url, headers=self.headers, timeout=45)
                except Exception as e:
                    logger.warning(f"Попытка {attempt + 1}: ошибка запроса - {e}")
                    continue
                
                if response.status_code != 200:
                    logger.warning(f"Попытка {attempt + 1}: статус {response.status_code}")
                    continue
                
                result = response.json()
                
                if 'results' in result and 'generation_data' in result['results']:
                    data = result['results']['generation_data']
                    status = data.get('status')
                    result_url = data.get('result_url')
                    status_description = data.get('status_description', '')
                    
                    logger.info(f"Попытка {attempt + 1}: статус={status}, описание={status_description}, result_url={result_url}")
                    
                    # Статусы API:
                    # 0 - в очереди
                    # 1 - в обработке
                    # 2 - успешно завершено
                    # 3 - ошибка
                    # 4 - таймаут
                    
                    if status == 2 and result_url:
                        return {
                            "status": "success",
                            "image_url": result_url,
                            "completed": True
                        }
                    elif status == 3:
                        error_msg = data.get('comment_ru') or data.get('comment_en') or "Ошибка генерации"
                        return {
                            "status": "failed", 
                            "error": error_msg,
                            "completed": True
                        }
                    elif status == 4:
                        return {
                            "status": "timeout", 
                            "error": "Таймаут генерации",
                            "completed": True
                        }
                
                if attempt == max_attempts - 1:
                    return {"status": "timeout", "error": "Превышено максимальное количество попыток", "completed": True}
                    
        except Exception as e:
            logger.error(f"Ошибка при получении результата: {e}")
            return {"status": "error", "error": str(e), "completed": True}
    
    def download_and_save_image(self, image_url: str) -> Optional[str]:
        """Скачивает изображение по URL и сохраняет локально"""
        try:
            logger.info(f"Скачивание изображения: {image_url}")
            response = requests.get(image_url, timeout=60)
            
            if response.status_code != 200:
                logger.error(f"Ошибка скачивания: статус {response.status_code}")
                return None
            
            # Определяем расширение по Content-Type
            content_type = response.headers.get('Content-Type', '')
            if 'png' in content_type:
                ext = 'png'
            elif 'jpeg' in content_type or 'jpg' in content_type:
                ext = 'jpg'
            else:
                ext = 'png'
            
            filename = f"{uuid.uuid4()}.{ext}"
            filepath = os.path.join(IMAGES_FOLDER, filename)
            
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                logger.info(f"Изображение сохранено: {filepath}")
                return filepath
            return None
            
        except Exception as e:
            logger.error(f"Ошибка при скачивании: {e}")
            return None

def build_prompt(base_prompt: str, toggles: dict) -> str:
    """Строит финальный промпт"""
    toggle_texts = {
        'price_tags': "проанализируй картинку, это стеллаж с товарами, посмотри где не хватает ценников под товаром, помести туда ценник, исходя из соседних ценников",
        'random_angle': "поменяй случайно ракурс фотографии, учитывай что эту фотографию делает человек и ракурс не может быть слишком высоким или слишком низким, так же учитывай что товары и ценники должны быть хорошо видны",
        'messy_shelf': "проанализируй картинку, это стеллаж с товарами, представь что в течение дня покупатели взаимодействовали с этой полкой, случайным образом убери часть товаров",
        'professional_arrangement': "проанализируй картинку, это стеллаж с товарами, представь что пришел мерчендайзер и выставил все товары, которых не хватало, добавил ценники, которых не хватало",
        'auto_fix': "проанализируй картинку, это стеллаж с товарами, сделай профессиональную выкладку товаров на полках"
    }
    
    active_texts = []
    for toggle_id, is_active in toggles.items():
        if is_active and toggle_id in toggle_texts:
            active_texts.append(toggle_texts[toggle_id])
    
    if not active_texts:
        return base_prompt.strip() if base_prompt else ""
    
    if not base_prompt or not base_prompt.strip():
        return ". ".join(active_texts)
    
    return f"{base_prompt.strip()}. {' '.join(active_texts)}"

def process_uploaded_files(uploaded_files):
    """Обрабатывает загруженные файлы"""
    if not uploaded_files:
        return []
    
    if len(uploaded_files) > 10:
        st.warning("Можно загрузить не более 10 изображений")
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
            
            if len(bytes_data) > 32 * 1024 * 1024:
                st.warning(f"❌ {uploaded_file.name} превышает 32 МБ")
                continue
            
            generator = ImageGenerator()
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
                    "file_key": file_key
                }
                
                st.session_state.uploaded_files_cache[file_key] = image_info
                processed_images.append(image_info)
                status_text.text(f"✅ {uploaded_file.name} загружен")
            
            progress_bar.progress((i + 1) / len(uploaded_files))
            
        except Exception as e:
            st.error(f"Ошибка при обработке {uploaded_file.name}: {str(e)}")
    
    progress_bar.empty()
    status_text.empty()
    return processed_images

def main():
    """Основная функция Streamlit приложения"""
    
    st.set_page_config(
        page_title="Генератор изображений",
        page_icon="🎨",
        layout="wide"
    )
    
    # Загружаем сохраненное состояние
    saved_state = load_state_from_file()
    
    # Инициализация session state
    if 'generator' not in st.session_state:
        st.session_state.generator = ImageGenerator()
    
    if 'uploaded_images' not in st.session_state:
        st.session_state.uploaded_images = []
    
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    
    if 'generation_started' not in st.session_state:
        st.session_state.generation_started = False
    
    if 'stop_generation' not in st.session_state:
        st.session_state.stop_generation = False
    
    # Загружаем результаты из сохраненного состояния
    if 'last_result_path' not in st.session_state:
        if saved_state and saved_state.get('last_result_path'):
            if os.path.exists(saved_state['last_result_path']):
                st.session_state.last_result_path = saved_state['last_result_path']
                logger.info(f"Загружен результат из файла: {saved_state['last_result_path']}")
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
    
    st.title("🎨 Генератор изображений")
    st.markdown("---")
    
    # Боковая панель
    with st.sidebar:
        st.header("ℹ️ Информация")
        st.markdown(f"ID: `{st.session_state.customer_id}`")
        st.markdown(f"📎 {len(st.session_state.uploaded_images)}/10 изображений")
        st.markdown("📐 Формат: 9:16 (вертикальный)")
        
        # Индикатор статуса генерации
        if st.session_state.processing:
            st.warning("⏳ Идет генерация...")
            if st.button("⏹️ Остановить генерацию", use_container_width=True):
                st.session_state.stop_generation = True
                st.rerun()
        elif st.session_state.generation_completed:
            st.success("✅ Генерация завершена")
        
        # Кнопка показа результата
        if st.session_state.last_result_path and os.path.exists(st.session_state.last_result_path):
            if st.button("🖼️ Показать результат", use_container_width=True):
                st.session_state.generation_completed = True
                st.rerun()
        
        if st.button("🗑️ Очистить всё", use_container_width=True):
            # Очищаем все состояния
            st.session_state.uploaded_files_cache = {}
            st.session_state.uploaded_images = []
            st.session_state.last_result_path = None
            st.session_state.last_result_url = None
            st.session_state.generation_completed = False
            st.session_state.task_id = None
            st.session_state.processing = False
            st.session_state.generation_started = False
            st.session_state.stop_generation = False
            
            # Удаляем файл состояния
            if os.path.exists(STATE_FILE):
                os.remove(STATE_FILE)
            
            # Удаляем сохраненные изображения
            for filename in os.listdir(IMAGES_FOLDER):
                filepath = os.path.join(IMAGES_FOLDER, filename)
                if os.path.isfile(filepath):
                    os.remove(filepath)
            
            st.success("✅ Очищено")
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
        
        # Обработка загруженных файлов
        if uploaded_files:
            current_files_key = str([(f.name, f.size) for f in uploaded_files])
            
            if ('last_files_key' not in st.session_state or 
                st.session_state.last_files_key != current_files_key):
                
                st.session_state.last_files_key = current_files_key
                new_images = process_uploaded_files(uploaded_files)
                if new_images:
                    st.session_state.uploaded_images = new_images
                    st.success(f"✅ Загружено {len(new_images)} изображений")
        
        # Превью загруженных изображений
        if st.session_state.uploaded_images:
            st.subheader("🖼️ Превью")
            cols = st.columns(min(len(st.session_state.uploaded_images), 5))
            for i, img_data in enumerate(st.session_state.uploaded_images[:5]):
                with cols[i]:
                    if img_data["thumbnail"]:
                        st.image(img_data["thumbnail"], use_column_width=True)
                    st.caption(f"{i+1}. {img_data['name'][:10]}...")
    
    with col2:
        st.subheader("📝 Настройки")
        
        # Поле для промпта
        base_prompt = st.text_area(
            "Описание (необязательно):",
            value=st.session_state.current_prompt,
            height=80,
            placeholder="Например: стеллаж с продуктами в магазине...",
            disabled=st.session_state.processing,
            key="base_prompt_input"
        )
        
        if base_prompt != st.session_state.current_prompt:
            st.session_state.current_prompt = base_prompt
            save_state_to_file()
        
        # Тумблеры
        st.markdown("### 🎛️ Параметры")
        
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            price_tags = st.toggle(
                "🏷️ Добавить ценники", 
                value=st.session_state.toggle_states['price_tags'], 
                key="t1", 
                disabled=st.session_state.processing,
                help="Анализирует где не хватает ценников и добавляет их"
            )
            random_angle = st.toggle(
                "🔄 Случайный ракурс", 
                value=st.session_state.toggle_states['random_angle'], 
                key="t2", 
                disabled=st.session_state.processing,
                help="Меняет ракурс фотографии (естественный, человеческий)"
            )
            messy_shelf = st.toggle(
                "📦 Неопрятная полка", 
                value=st.session_state.toggle_states['messy_shelf'], 
                key="t3", 
                disabled=st.session_state.processing,
                help="Имитирует взаимодействие покупателей - часть товаров убрана"
            )
        with col_t2:
            professional = st.toggle(
                "✨ Профессиональная выкладка", 
                value=st.session_state.toggle_states['professional_arrangement'], 
                key="t4", 
                disabled=st.session_state.processing,
                help="Мерчендайзер выставил все товары и добавил ценники"
            )
            auto_fix = st.toggle(
                "🔧 Автоисправление", 
                value=st.session_state.toggle_states['auto_fix'], 
                key="t5", 
                disabled=st.session_state.processing,
                help="Делает профессиональную выкладку товаров"
            )
        
        # Обновляем состояния тумблеров
        new_toggle_states = {
            'price_tags': price_tags,
            'random_angle': random_angle,
            'messy_shelf': messy_shelf,
            'professional_arrangement': professional,
            'auto_fix': auto_fix
        }
        
        if new_toggle_states != st.session_state.toggle_states:
            st.session_state.toggle_states = new_toggle_states
            save_state_to_file()
        
        # Финальный промпт
        final_prompt = build_prompt(st.session_state.current_prompt, st.session_state.toggle_states)
        if final_prompt:
            with st.expander("📝 Финальный промпт", expanded=False):
                st.write(final_prompt)
        
        # Кнопка генерации
        has_images = len(st.session_state.uploaded_images) > 0
        can_generate = has_images and not st.session_state.processing
        
        if not has_images:
            st.warning("⚠️ Сначала загрузите изображения")
        
        generate_button = st.button(
            "🚀 Сгенерировать",
            type="primary",
            use_container_width=True,
            disabled=not can_generate
        )
        
        # Область для результата
        result_placeholder = st.empty()
        
        # Если есть результат - показываем его
        if st.session_state.generation_completed and st.session_state.last_result_path:
            if os.path.exists(st.session_state.last_result_path):
                with result_placeholder.container():
                    st.subheader("🎨 Результат")
                    st.image(st.session_state.last_result_path, use_column_width=True)
                    
                    with open(st.session_state.last_result_path, "rb") as file:
                        st.download_button(
                            label="📥 Скачать",
                            data=file,
                            file_name="generated.png",
                            mime="image/png",
                            use_container_width=True
                        )
        
        # Область для статуса
        status_placeholder = st.empty()
        
        # Обработка генерации
        if generate_button and not st.session_state.processing:
            st.session_state.processing = True
            st.session_state.generation_started = True
            st.session_state.stop_generation = False
            st.session_state.task_id = None
            st.session_state.generation_completed = False
            
            try:
                references_urls = [img["url"] for img in st.session_state.uploaded_images if "url" in img]
                
                if not references_urls:
                    status_placeholder.error("❌ Нет URL изображений")
                    st.session_state.processing = False
                    st.session_state.generation_started = False
                    return
                
                status_placeholder.info("🔄 Отправка запроса...")
                
                gen_result = st.session_state.generator.generate_multi_image(
                    final_prompt, 
                    references_urls, 
                    st.session_state.customer_id
                )
                
                if gen_result and "error" not in gen_result:
                    if 'results' in gen_result and 'generation_data' in gen_result['results']:
                        api_task_id = gen_result['results']['generation_data']['id']
                        st.session_state.task_id = api_task_id
                        
                        status_placeholder.info(f"🆔 ID: {api_task_id}\n\n⏳ Ожидание результата... (обычно 30-60 секунд)")
                        save_state_to_file()
                        
                        # Получаем результат с увеличенным количеством попыток
                        task_result = None
                        max_attempts = 60  # Увеличили до 60 попыток
                        
                        for attempt in range(max_attempts):
                            if st.session_state.stop_generation:
                                status_placeholder.warning("⏹️ Генерация остановлена пользователем")
                                st.session_state.processing = False
                                st.session_state.generation_started = False
                                return
                            
                            # Обновляем статус каждые 10 попыток
                            if attempt % 10 == 0 and attempt > 0:
                                status_placeholder.info(f"🆔 ID: {api_task_id}\n\n⏳ Ожидание... прошло {attempt*5} секунд")
                            
                            task_result = st.session_state.generator.get_task_result(api_task_id, max_attempts=1, wait_time=5)
                            
                            if task_result and task_result.get("completed", False):
                                break
                            
                            time.sleep(1)
                        
                        if task_result and task_result.get("completed", False):
                            if task_result.get("status") == "success":
                                image_url = task_result.get("image_url")
                                
                                if image_url:
                                    st.session_state.last_result_url = image_url
                                    status_placeholder.info("📥 Скачивание изображения...")
                                    save_state_to_file()
                                    
                                    local_path = st.session_state.generator.download_and_save_image(image_url)
                                    
                                    if local_path:
                                        st.session_state.last_result_path = local_path
                                        st.session_state.generation_completed = True
                                        
                                        # Сохраняем состояние
                                        save_state_to_file()
                                        
                                        # Очищаем статус и флаги
                                        status_placeholder.empty()
                                        st.session_state.processing = False
                                        st.session_state.generation_started = False
                                        
                                        # Показываем результат
                                        st.rerun()
                                    else:
                                        status_placeholder.error("❌ Ошибка сохранения изображения")
                                        st.session_state.processing = False
                                        st.session_state.generation_started = False
                                else:
                                    status_placeholder.error("❌ Не получен URL изображения")
                                    st.session_state.processing = False
                                    st.session_state.generation_started = False
                            else:
                                error_msg = task_result.get('error', 'Неизвестная ошибка')
                                status_placeholder.error(f"❌ Ошибка генерации: {error_msg}")
                                st.session_state.processing = False
                                st.session_state.generation_started = False
                        else:
                            status_placeholder.error("❌ Превышено время ожидания (5 минут). Попробуйте снова.")
                            st.session_state.processing = False
                            st.session_state.generation_started = False
                    else:
                        status_placeholder.error("❌ Ошибка API: неверный формат ответа")
                        st.session_state.processing = False
                        st.session_state.generation_started = False
                else:
                    error_msg = gen_result.get("message", "Неизвестная ошибка") if gen_result else "Ошибка подключения к API"
                    status_placeholder.error(f"❌ {error_msg}")
                    st.session_state.processing = False
                    st.session_state.generation_started = False
                
            except Exception as e:
                status_placeholder.error(f"❌ Ошибка: {str(e)}")
                logger.error(f"Ошибка: {e}")
                st.session_state.processing = False
                st.session_state.generation_started = False

if __name__ == "__main__":
    main()
