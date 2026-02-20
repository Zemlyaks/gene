import streamlit as st
import requests
import json
import logging
import base64
import io
import time
from PIL import Image
from typing import List, Optional
import hashlib

# Настройка логирования
logging.basicConfig(level=logging.WARNING)  # Уменьшаем количество логов
logger = logging.getLogger(__name__)

# Конфигурация API
API_KEY = "dk-13a00e5103d9345a25a6df802988ad47"
API_URL_GEN = "https://api.defapi.org/api/image/gen"
API_URL_QUERY = "https://api.defapi.org/api/task/query"

# Кэш для обработанных изображений
@st.cache_data(ttl=3600, show_spinner=False)
def process_image_cache(image_bytes: bytes) -> Optional[dict]:
    """Кэширует обработанные изображения"""
    try:
        # Открываем изображение
        image = Image.open(io.BytesIO(image_bytes))
        
        # Конвертируем в RGB если нужно
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Сжимаем изображение до разумного размера
        max_size = 1024
        if max(image.size) > max_size:
            ratio = max_size / max(image.size)
            new_size = tuple(int(dim * ratio) for dim in image.size)
            image = image.resize(new_size, Image.Resampling.LANCZOS)
        
        # Сохраняем в JPEG с качеством 85
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=85, optimize=True)
        compressed_bytes = buffer.getvalue()
        
        # Конвертируем в base64
        base64_image = base64.b64encode(compressed_bytes).decode('utf-8')
        
        # Создаем хеш для идентификации
        image_hash = hashlib.md5(compressed_bytes).hexdigest()[:8]
        
        return {
            "data": base64_image,
            "mime_type": "image/jpeg",
            "hash": image_hash,
            "size": len(compressed_bytes)
        }
        
    except Exception as e:
        logger.error(f"Ошибка при обработке изображения: {e}")
        return None

class ImageGenerator:
    """Класс для генерации изображений через API"""
    
    def __init__(self):
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        }
    
    def generate_multi_image(self, prompt: str, images_data: List[dict]) -> dict:
        """Генерирует изображение на основе промпта и загруженных изображений"""
        
        if not images_data:
            return {"error": "Нет изображений для обработки"}
        
        # Подготавливаем изображения для API
        processed_images = []
        for img_data in images_data:
            data_url = f"data:{img_data['mime_type']};base64,{img_data['data']}"
            processed_images.append(data_url)
        
        # Формируем запрос
        data = {
            "model": "google/nano-banana",
            "prompt": prompt,
            "images": processed_images,
            "parameters": {
                "negative_prompt": "",
                "cfg_scale": 7,
                "steps": 20,
                "width": 1024,
                "height": 1024,
                "sampler": "DPM++ 2M Karras"
            }
        }
        
        try:
            logger.info(f"Отправка запроса к API с {len(images_data)} изображениями")
            
            response = requests.post(
                API_URL_GEN, 
                headers=self.headers, 
                json=data, 
                timeout=120
            )
            
            if response.status_code != 200:
                try:
                    error_data = response.json()
                    return {"error": f"API ошибка: {error_data.get('message', 'Unknown error')}"}
                except:
                    return {"error": f"HTTP {response.status_code}"}
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Ошибка при генерации: {e}")
            return {"error": str(e)}
    
    def get_task_result(self, task_id: str) -> Optional[str]:
        """Получает результат задачи по task_id"""
        try:
            url = f"{API_URL_QUERY}?task_id={task_id}"
            
            max_attempts = 30
            for attempt in range(max_attempts):
                time.sleep(2)
                
                try:
                    response = requests.get(url, headers=self.headers, timeout=30)
                    
                    if response.status_code != 200:
                        continue
                    
                    result = response.json()
                    
                    if 'data' in result:
                        data = result['data']
                        status = data.get('status')
                        
                        if status == 'success':
                            if 'result' in data and data['result']:
                                if isinstance(data['result'], list) and len(data['result']) > 0:
                                    return data['result'][0].get('image')
                                elif isinstance(data['result'], dict):
                                    return data['result'].get('image')
                            return None
                        
                        elif status in ['failed', 'error']:
                            return None
                    
                except Exception:
                    continue
                    
            return None
            
        except Exception as e:
            logger.error(f"Ошибка при получении результата: {e}")
            return None

def init_session_state():
    """Инициализация состояния сессии"""
    if 'generator' not in st.session_state:
        st.session_state.generator = ImageGenerator()
    
    if 'uploaded_images' not in st.session_state:
        st.session_state.uploaded_images = []
    
    if 'processed_hashes' not in st.session_state:
        st.session_state.processed_hashes = set()
    
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    
    if 'last_result' not in st.session_state:
        st.session_state.last_result = None
    
    if 'error_message' not in st.session_state:
        st.session_state.error_message = None

def clear_all():
    """Очищает все данные"""
    st.session_state.uploaded_images = []
    st.session_state.processed_hashes = set()
    st.session_state.last_result = None
    st.session_state.error_message = None
    st.session_state.processing = False

def main():
    """Основная функция Streamlit приложения"""
    
    # Настройка страницы
    st.set_page_config(
        page_title="Генератор изображений",
        page_icon="🎨",
        layout="wide"
    )
    
    # Инициализация состояния
    init_session_state()
    
    # Заголовок
    st.title("🎨 Генератор изображений")
    st.markdown("---")
    
    # Боковая панель
    with st.sidebar:
        st.header("ℹ️ Информация")
        st.markdown("""
        **Как это работает:**
        1. Загрузите до 4 изображений
        2. Напишите промпт
        3. Нажмите "Сгенерировать"
        4. Подождите 30-60 секунд
        """)
        
        st.markdown("---")
        st.markdown(f"**Загружено:** {len(st.session_state.uploaded_images)}/4")
        
        if st.button("🗑️ Очистить всё", use_container_width=True):
            clear_all()
            st.rerun()
    
    # Отображение ошибки
    if st.session_state.error_message:
        st.error(st.session_state.error_message)
        if st.button("Очистить ошибку"):
            st.session_state.error_message = None
            st.rerun()
    
    # Основной контент
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📤 Загрузка изображений")
        
        # Загрузка файлов
        uploaded_files = st.file_uploader(
            "Выберите изображения",
            type=['png', 'jpg', 'jpeg', 'webp'],
            accept_multiple_files=True,
            key="file_uploader",
            disabled=st.session_state.processing
        )
        
        # Обработка новых файлов (только если есть новые)
        if uploaded_files and not st.session_state.processing:
            new_images = []
            
            for uploaded_file in uploaded_files:
                try:
                    bytes_data = uploaded_file.getvalue()
                    
                    # Проверяем размер
                    if len(bytes_data) > 10 * 1024 * 1024:
                        st.warning(f"Файл {uploaded_file.name} слишком большой (>10MB)")
                        continue
                    
                    # Проверяем лимит
                    if len(st.session_state.uploaded_images) + len(new_images) >= 4:
                        st.warning("Максимум 4 изображения")
                        break
                    
                    # Обрабатываем через кэш
                    processed = process_image_cache(bytes_data)
                    
                    if processed and processed['hash'] not in st.session_state.processed_hashes:
                        new_images.append({
                            "data": processed,
                            "name": uploaded_file.name,
                            "thumbnail": bytes_data,
                            "hash": processed['hash']
                        })
                        st.session_state.processed_hashes.add(processed['hash'])
                    
                except Exception as e:
                    st.error(f"Ошибка при обработке {uploaded_file.name}")
            
            # Добавляем новые изображения
            if new_images:
                st.session_state.uploaded_images.extend(new_images)
                st.rerun()
        
        # Отображение загруженных изображений
        if st.session_state.uploaded_images:
            st.subheader("🖼️ Загруженные")
            cols = st.columns(min(len(st.session_state.uploaded_images), 4))
            
            for idx, img_data in enumerate(st.session_state.uploaded_images):
                with cols[idx % 4]:
                    st.image(
                        img_data["thumbnail"],
                        caption=f"{idx+1}. {img_data['name'][:10]}...",
                        use_column_width=True
                    )
    
    with col2:
        st.subheader("📝 Промпт и генерация")
        
        # Поле для промпта
        prompt = st.text_area(
            "Опишите желаемый результат:",
            height=100,
            placeholder="Например: Объедините изображения в один коллаж",
            disabled=st.session_state.processing,
            key="prompt_input"
        )
        
        # Проверяем, можно ли генерировать
        can_generate = (
            not st.session_state.processing and 
            len(st.session_state.uploaded_images) > 0 and 
            prompt and 
            len(prompt.strip()) >= 3
        )
        
        # Кнопка генерации
        if st.button(
            "🚀 Сгенерировать",
            type="primary",
            use_container_width=True,
            disabled=not can_generate
        ):
            st.session_state.processing = True
            st.session_state.error_message = None
            
            # Создаем контейнеры для прогресса
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                status_text.text("Подготовка данных...")
                progress_bar.progress(10)
                
                # Подготавливаем данные
                images_data = [img["data"] for img in st.session_state.uploaded_images]
                
                status_text.text("Отправка запроса к API...")
                progress_bar.progress(20)
                
                # Отправляем запрос
                gen_result = st.session_state.generator.generate_multi_image(prompt, images_data)
                
                if gen_result and "error" not in gen_result:
                    if 'data' in gen_result and 'task_id' in gen_result['data']:
                        task_id = gen_result['data']['task_id']
                        
                        status_text.text("Ожидание результата...")
                        
                        # Ждем результат
                        for i in range(30):
                            progress_bar.progress(20 + i * 2)
                            time.sleep(1)
                        
                        image_url = st.session_state.generator.get_task_result(task_id)
                        
                        if image_url:
                            st.session_state.last_result = image_url
                            status_text.text("Готово!")
                            progress_bar.progress(100)
                            time.sleep(1)
                        else:
                            st.session_state.error_message = "Не удалось получить результат"
                    else:
                        st.session_state.error_message = "Неверный ответ от API"
                else:
                    error_msg = gen_result.get("error", "Неизвестная ошибка") if gen_result else "Ошибка подключения"
                    st.session_state.error_message = f"Ошибка: {error_msg}"
                    
            except Exception as e:
                st.session_state.error_message = f"Ошибка: {str(e)}"
            
            finally:
                progress_bar.empty()
                status_text.empty()
                st.session_state.processing = False
                st.rerun()
        
        # Отображение результата
        if st.session_state.last_result:
            st.subheader("🎨 Результат")
            st.image(st.session_state.last_result, use_column_width=True)
            
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("🔄 Новый запрос", use_container_width=True):
                    st.session_state.last_result = None
                    st.rerun()
            with col_b:
                st.markdown(f"[📥 Скачать]({st.session_state.last_result})")

if __name__ == "__main__":
    main()
