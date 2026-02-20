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
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация API
API_KEY = "dk-13a00e5103d9345a25a6df802988ad47"
API_URL_GEN = "https://api.defapi.org/api/image/gen"
API_URL_QUERY = "https://api.defapi.org/api/task/query"

@st.cache_data(ttl=3600, show_spinner=False)
def process_image_cache(image_bytes: bytes) -> Optional[dict]:
    """Кэширует обработанные изображения"""
    try:
        image = Image.open(io.BytesIO(image_bytes))
        
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Уменьшаем размер для уменьшения нагрузки на API
        max_size = 768  # Уменьшил с 1024 до 768
        if max(image.size) > max_size:
            ratio = max_size / max(image.size)
            new_size = tuple(int(dim * ratio) for dim in image.size)
            image = image.resize(new_size, Image.Resampling.LANCZOS)
        
        # Увеличиваем сжатие для уменьшения размера
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=75, optimize=True)  # Уменьшил quality с 85 до 75
        compressed_bytes = buffer.getvalue()
        
        base64_image = base64.b64encode(compressed_bytes).decode('utf-8')
        image_hash = hashlib.md5(compressed_bytes).hexdigest()[:8]
        
        logger.info(f"Изображение обработано: размер base64={len(base64_image)}")
        
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
    def __init__(self):
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        }
    
    def generate_multi_image(self, prompt: str, images_data: List[dict]) -> dict:
        """Генерирует изображение с подробным логированием"""
        
        if not images_data:
            return {"error": "Нет изображений для обработки"}
        
        # Подготавливаем изображения
        processed_images = []
        for i, img_data in enumerate(images_data):
            data_url = f"data:{img_data['mime_type']};base64,{img_data['data']}"
            processed_images.append(data_url)
            logger.info(f"Изображение {i+1}: длина data URL = {len(data_url)}")
        
        # Пробуем разные форматы запроса
        # Вариант 1: images как массив
        data_v1 = {
            "model": "google/nano-banana",
            "prompt": prompt,
            "images": processed_images
        }
        
        # Вариант 2: с параметрами
        data_v2 = {
            "model": "google/nano-banana",
            "prompt": prompt,
            "images": processed_images,
            "parameters": {
                "negative_prompt": "",
                "cfg_scale": 7,
                "steps": 20,
                "width": 512,  # Уменьшил размер
                "height": 512,
                "sampler": "DPM++ 2M Karras"
            }
        }
        
        # Вариант 3: images как объект
        data_v3 = {
            "model": "google/nano-banana",
            "prompt": prompt,
            "images": {"0": processed_images[0]} if len(processed_images) == 1 else dict(enumerate(processed_images))
        }
        
        # Пробуем каждый вариант
        for version, data in [("v1", data_v1), ("v2", data_v2), ("v3", data_v3)]:
            try:
                logger.info(f"Пробуем вариант {version}")
                logger.info(f"URL: {API_URL_GEN}")
                logger.info(f"Headers: { {k: '***' if 'Bearer' in v else v for k, v in self.headers.items()} }")
                logger.info(f"Data keys: {list(data.keys())}")
                
                response = requests.post(
                    API_URL_GEN, 
                    headers=self.headers, 
                    json=data, 
                    timeout=30
                )
                
                logger.info(f"Статус ответа для {version}: {response.status_code}")
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"Успешный ответ для {version}")
                    return result
                else:
                    logger.error(f"Ошибка для {version}: {response.status_code}")
                    logger.error(f"Response text: {response.text[:500]}")
                    
            except Exception as e:
                logger.error(f"Исключение для {version}: {str(e)}")
                continue
        
        return {"error": "Все варианты запроса не удались"}
    
    def get_task_result(self, task_id: str) -> Optional[str]:
        """Получает результат задачи"""
        try:
            url = f"{API_URL_QUERY}?task_id={task_id}"
            logger.info(f"Проверка статуса задачи: {task_id}")
            
            max_attempts = 30
            for attempt in range(max_attempts):
                time.sleep(2)
                
                try:
                    response = requests.get(url, headers=self.headers, timeout=30)
                    
                    if response.status_code != 200:
                        logger.warning(f"Попытка {attempt+1}: статус {response.status_code}")
                        continue
                    
                    result = response.json()
                    logger.info(f"Попытка {attempt+1}: {result}")
                    
                    if 'data' in result:
                        data = result['data']
                        status = data.get('status')
                        
                        if status == 'success':
                            if 'result' in data and data['result']:
                                if isinstance(data['result'], list) and len(data['result']) > 0:
                                    image_url = data['result'][0].get('image')
                                    logger.info(f"Получен URL: {image_url}")
                                    return image_url
                            return None
                        
                        elif status in ['failed', 'error']:
                            logger.error(f"Задача завершилась с ошибкой: {data.get('message')}")
                            return None
                    
                except Exception as e:
                    logger.error(f"Ошибка при проверке статуса: {e}")
                    
            return None
            
        except Exception as e:
            logger.error(f"Ошибка при получении результата: {e}")
            return None

def init_session_state():
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
    if 'debug_info' not in st.session_state:
        st.session_state.debug_info = None

def clear_all():
    st.session_state.uploaded_images = []
    st.session_state.processed_hashes = set()
    st.session_state.last_result = None
    st.session_state.error_message = None
    st.session_state.processing = False
    st.session_state.debug_info = None

def main():
    st.set_page_config(
        page_title="Генератор изображений",
        page_icon="🎨",
        layout="wide"
    )
    
    init_session_state()
    
    st.title("🎨 Генератор изображений")
    st.markdown("---")
    
    # Debug секция (только для разработки)
    with st.expander("🔧 Debug информация", expanded=False):
        if st.session_state.debug_info:
            st.json(st.session_state.debug_info)
        if st.button("Очистить debug"):
            st.session_state.debug_info = None
    
    with st.sidebar:
        st.header("ℹ️ Информация")
        st.markdown("""
        **Как это работает:**
        1. Загрузите до 4 изображений
        2. Напишите промпт
        3. Нажмите "Сгенерировать"
        """)
        
        st.markdown("---")
        st.markdown(f"**Загружено:** {len(st.session_state.uploaded_images)}/4")
        
        if st.button("🗑️ Очистить всё", use_container_width=True):
            clear_all()
            st.rerun()
    
    if st.session_state.error_message:
        st.error(st.session_state.error_message)
        if st.button("Очистить ошибку"):
            st.session_state.error_message = None
            st.rerun()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📤 Загрузка изображений")
        
        uploaded_files = st.file_uploader(
            "Выберите изображения",
            type=['png', 'jpg', 'jpeg', 'webp'],
            accept_multiple_files=True,
            key="file_uploader",
            disabled=st.session_state.processing
        )
        
        if uploaded_files and not st.session_state.processing:
            new_images = []
            
            for uploaded_file in uploaded_files:
                try:
                    bytes_data = uploaded_file.getvalue()
                    
                    if len(bytes_data) > 10 * 1024 * 1024:
                        st.warning(f"Файл {uploaded_file.name} слишком большой (>10MB)")
                        continue
                    
                    if len(st.session_state.uploaded_images) + len(new_images) >= 4:
                        st.warning("Максимум 4 изображения")
                        break
                    
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
            
            if new_images:
                st.session_state.uploaded_images.extend(new_images)
                st.rerun()
        
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
        
        prompt = st.text_area(
            "Опишите желаемый результат:",
            height=100,
            placeholder="Например: Объедините изображения в один коллаж",
            disabled=st.session_state.processing,
            key="prompt_input"
        )
        
        can_generate = (
            not st.session_state.processing and 
            len(st.session_state.uploaded_images) > 0 and 
            prompt and 
            len(prompt.strip()) >= 3
        )
        
        if st.button(
            "🚀 Сгенерировать",
            type="primary",
            use_container_width=True,
            disabled=not can_generate
        ):
            st.session_state.processing = True
            st.session_state.error_message = None
            st.session_state.debug_info = None
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                status_text.text("Подготовка данных...")
                progress_bar.progress(10)
                
                images_data = [img["data"] for img in st.session_state.uploaded_images]
                
                status_text.text("Отправка запроса к API...")
                progress_bar.progress(20)
                
                # Сохраняем debug информацию
                st.session_state.debug_info = {
                    "prompt": prompt,
                    "num_images": len(images_data),
                    "image_sizes": [len(img["data"]) for img in images_data]
                }
                
                gen_result = st.session_state.generator.generate_multi_image(prompt, images_data)
                
                # Обновляем debug информацией с ответом
                st.session_state.debug_info["response"] = gen_result
                
                if gen_result and "error" not in gen_result:
                    if 'data' in gen_result and 'task_id' in gen_result['data']:
                        task_id = gen_result['data']['task_id']
                        st.session_state.debug_info["task_id"] = task_id
                        
                        status_text.text("Ожидание результата...")
                        
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
                        st.session_state.error_message = f"Неверный ответ от API: {gen_result}"
                else:
                    error_msg = gen_result.get("error", "Неизвестная ошибка") if gen_result else "Ошибка подключения"
                    st.session_state.error_message = f"Ошибка: {error_msg}"
                    
            except Exception as e:
                st.session_state.error_message = f"Ошибка: {str(e)}"
                st.session_state.debug_info["exception"] = str(e)
            
            finally:
                progress_bar.empty()
                status_text.empty()
                st.session_state.processing = False
                st.rerun()
        
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
