import streamlit as st
import requests
import json
import logging
import base64
import io
import time
from PIL import Image
from typing import List, Optional

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация API - та же что и в Telegram боте
API_KEY = "dk-13a00e5103d9345a25a6df802988ad47"
API_URL_GEN = "https://api.defapi.org/api/image/gen"
API_URL_QUERY = "https://api.defapi.org/api/task/query"

class ImageGenerator:
    """Класс для генерации изображений - скопирован из Telegram бота"""
    
    def __init__(self):
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        }
    
    def download_and_process_image(self, image_bytes: bytes) -> dict:
        """Обрабатывает изображение как в Telegram боте"""
        try:
            # Пробуем определить тип изображения
            try:
                image = Image.open(io.BytesIO(image_bytes))
                format_str = image.format
                
                if format_str == 'JPEG':
                    mime_type = "image/jpeg"
                elif format_str == 'PNG':
                    mime_type = "image/png"
                elif format_str == 'GIF':
                    mime_type = "image/gif"
                elif format_str == 'WEBP':
                    mime_type = "image/webp"
                else:
                    mime_type = "image/jpeg"
                    
                image.close()
            except Exception:
                mime_type = "image/jpeg"
            
            # Конвертируем в base64
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            
            logger.info(f"Изображение обработано: {mime_type}, размер: {len(base64_image)} символов")
            
            return {
                "data": base64_image,
                "mime_type": mime_type
            }
            
        except Exception as e:
            logger.error(f"Ошибка при обработке изображения: {e}")
            return None

    def generate_multi_image(self, prompt: str, images_data: List[dict]) -> dict:
        """Генерация изображения с несколькими входными изображениями - как в Telegram боте"""
        # Подготавливаем изображения для API
        processed_images = []
        for img_data in images_data:
            processed_images.append(f"data:{img_data['mime_type']};base64,{img_data['data']}")
        
        data = {
            "model": "google/nano-banana",
            "prompt": prompt,
            "images": processed_images
        }
        
        try:
            logger.info(f"Отправка multi-image запроса: {prompt} с {len(images_data)} изображениями")
            
            response = requests.post(API_URL_GEN, headers=self.headers, json=data, timeout=60)
            logger.info(f"Response status: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"HTTP Error: {response.status_code}, Response: {response.text}")
                return {"error": f"HTTP {response.status_code}: {response.text}"}
            
            result = response.json()
            logger.info(f"Ответ multi-image генерации: {result}")
            return result
            
        except requests.exceptions.Timeout:
            logger.error("Таймаут при multi-image генерации")
            return {"error": "timeout"}
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка при multi-image генерации: {e}")
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"Неожиданная ошибка: {e}")
            return {"error": str(e)}

    def get_task_result(self, task_id: str) -> dict:
        """Получение результата задачи - как в Telegram боте"""
        try:
            url = f"{API_URL_QUERY}?task_id={task_id}"
            logger.info(f"Запрос статуса задачи: {task_id}")
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            result = response.json()
            return result
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка при получении результата: {e}")
            return None

def init_session_state():
    if 'generator' not in st.session_state:
        st.session_state.generator = ImageGenerator()
    if 'uploaded_images' not in st.session_state:
        st.session_state.uploaded_images = []
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    if 'last_result' not in st.session_state:
        st.session_state.last_result = None
    if 'error_message' not in st.session_state:
        st.session_state.error_message = None

def clear_all():
    st.session_state.uploaded_images = []
    st.session_state.last_result = None
    st.session_state.error_message = None
    st.session_state.processing = False

def main():
    st.set_page_config(
        page_title="Генератор изображений",
        page_icon="🎨",
        layout="wide"
    )
    
    init_session_state()
    
    st.title("🎨 Генератор изображений")
    st.markdown("---")
    
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
            type=['png', 'jpg', 'jpeg', 'gif', 'webp'],
            accept_multiple_files=True,
            key="file_uploader",
            disabled=st.session_state.processing
        )
        
        if uploaded_files and not st.session_state.processing:
            for uploaded_file in uploaded_files:
                try:
                    if len(st.session_state.uploaded_images) >= 4:
                        st.warning("Максимум 4 изображения")
                        break
                    
                    bytes_data = uploaded_file.getvalue()
                    
                    # Обрабатываем как в Telegram боте
                    processed = st.session_state.generator.download_and_process_image(bytes_data)
                    
                    if processed:
                        st.session_state.uploaded_images.append({
                            "data": processed,
                            "name": uploaded_file.name,
                            "thumbnail": bytes_data
                        })
                        st.success(f"✅ {uploaded_file.name}")
                    
                except Exception as e:
                    st.error(f"Ошибка при обработке {uploaded_file.name}")
            
            if st.session_state.uploaded_images:
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
            disabled=st.session_state.processing
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
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                status_text.text("Подготовка данных...")
                progress_bar.progress(10)
                
                images_data = [img["data"] for img in st.session_state.uploaded_images]
                
                status_text.text("Отправка запроса к API...")
                progress_bar.progress(20)
                
                # Используем тот же метод что и в Telegram боте
                gen_result = st.session_state.generator.generate_multi_image(prompt, images_data)
                
                if gen_result and "error" not in gen_result:
                    if 'data' in gen_result and 'task_id' in gen_result['data']:
                        task_id = gen_result['data']['task_id']
                        
                        status_text.text("Ожидание результата...")
                        
                        # Ждем результат как в Telegram боте
                        max_attempts = 30
                        wait_time = 3
                        
                        for attempt in range(max_attempts):
                            time.sleep(wait_time)
                            progress_bar.progress(20 + (attempt * 2))
                            
                            task_result = st.session_state.generator.get_task_result(task_id)
                            
                            if task_result and 'data' in task_result:
                                data = task_result['data']
                                status = data.get('status')
                                
                                if status == 'success' and 'result' in data and data['result']:
                                    if isinstance(data['result'], list) and len(data['result']) > 0:
                                        image_url = data['result'][0].get('image')
                                    else:
                                        image_url = data['result'].get('image')
                                    
                                    if image_url:
                                        st.session_state.last_result = image_url
                                        status_text.text("Готово!")
                                        progress_bar.progress(100)
                                        break
                                
                                elif status in ['failed', 'error']:
                                    st.session_state.error_message = "Ошибка при генерации"
                                    break
                            
                            if attempt == max_attempts - 1:
                                st.session_state.error_message = "Превышено время ожидания"
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
