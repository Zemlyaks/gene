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

# Конфигурация API
API_KEY = "dk-13a00e5103d9345a25a6df802988ad47"
API_URL_GEN = "https://api.defapi.org/api/image/gen"
API_URL_QUERY = "https://api.defapi.org/api/task/query"

class ImageGenerator:
    """Класс для генерации изображений через API"""
    
    def __init__(self):
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        }
    
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
                'WEBP': "image/webp",
                'BMP': "image/bmp"
            }
            mime_type = mime_types.get(format_str, "image/jpeg")
            
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
        """Генерирует изображение на основе промпта и загруженных изображений"""
        
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
            logger.info(f"Отправка multi-image запроса: {prompt[:50]}... с {len(images_data)} изображениями")
            
            response = requests.post(
                API_URL_GEN, 
                headers=self.headers, 
                json=data, 
                timeout=60
            )
            
            if response.status_code != 200:
                logger.error(f"HTTP Error: {response.status_code}")
                return {"error": f"HTTP {response.status_code}"}
            
            result = response.json()
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при генерации: {e}")
            return {"error": str(e)}
    
    def get_task_result(self, task_id: str, max_attempts: int = 30) -> Optional[str]:
        """Получает результат задачи по task_id"""
        try:
            url = f"{API_URL_QUERY}?task_id={task_id}"
            
            for attempt in range(max_attempts):
                time.sleep(2)  # Ждем 2 секунды между попытками
                
                try:
                    response = requests.get(url, headers=self.headers, timeout=30)
                    
                    if response.status_code != 200:
                        continue
                    
                    result = response.json()
                    
                    if 'data' in result:
                        data = result['data']
                        status = data.get('status')
                        
                        if status == 'success' and 'result' in data and data['result']:
                            if isinstance(data['result'], list) and len(data['result']) > 0:
                                return data['result'][0].get('image')
                            elif isinstance(data['result'], dict):
                                return data['result'].get('image')
                        
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
    
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    
    if 'last_result' not in st.session_state:
        st.session_state.last_result = None
    
    if 'processed_files' not in st.session_state:
        st.session_state.processed_files = set()

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
    st.title("🎨 Генератор изображений из изображений")
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
            st.session_state.uploaded_images = []
            st.session_state.last_result = None
            st.session_state.processed_files = set()
            st.rerun()
    
    # Основной контент
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📤 Загрузка изображений")
        
        # Загрузка файлов
        uploaded_files = st.file_uploader(
            "Выберите изображения",
            type=['png', 'jpg', 'jpeg', 'gif', 'webp'],
            accept_multiple_files=True,
            key="file_uploader",
            disabled=st.session_state.processing
        )
        
        # Обработка новых файлов
        if uploaded_files and not st.session_state.processing:
            new_images = []
            
            for uploaded_file in uploaded_files:
                # Проверяем, не обрабатывали ли мы этот файл ранее
                file_id = f"{uploaded_file.name}_{uploaded_file.size}"
                
                if file_id not in st.session_state.processed_files:
                    try:
                        bytes_data = uploaded_file.getvalue()
                        
                        # Проверяем размер
                        if len(bytes_data) > 10 * 1024 * 1024:
                            st.warning(f"Файл {uploaded_file.name} слишком большой (>10MB)")
                            continue
                        
                        # Обрабатываем изображение
                        processed = st.session_state.generator.process_image(bytes_data)
                        
                        if processed:
                            new_images.append({
                                "data": processed,
                                "name": uploaded_file.name,
                                "thumbnail": bytes_data
                            })
                            st.session_state.processed_files.add(file_id)
                            
                    except Exception as e:
                        st.error(f"Ошибка при обработке {uploaded_file.name}")
            
            if new_images:
                # Добавляем новые изображения к существующим (не заменяем)
                st.session_state.uploaded_images.extend(new_images)
                # Ограничиваем до 4
                if len(st.session_state.uploaded_images) > 4:
                    st.session_state.uploaded_images = st.session_state.uploaded_images[:4]
                st.success(f"✅ Добавлено {len(new_images)} изображений")
                st.rerun()
        
        # Отображение загруженных изображений
        if st.session_state.uploaded_images:
            st.subheader("🖼️ Загруженные")
            cols = st.columns(min(len(st.session_state.uploaded_images), 4))
            
            for idx, img_data in enumerate(st.session_state.uploaded_images):
                with cols[idx % 4]:
                    st.image(
                        img_data["thumbnail"],
                        caption=f"IMG {idx+1}",
                        use_column_width=True
                    )
    
    with col2:
        st.subheader("📝 Промпт и генерация")
        
        # Поле для промпта
        prompt = st.text_area(
            "Опишите желаемый результат:",
            height=100,
            placeholder="Например: Объедините изображения в коллаж...",
            disabled=st.session_state.processing or len(st.session_state.uploaded_images) == 0,
            key="prompt_input"
        )
        
        # Кнопка генерации
        if st.button(
            "🚀 Сгенерировать",
            type="primary",
            use_container_width=True,
            disabled=(
                st.session_state.processing or 
                len(st.session_state.uploaded_images) == 0 or 
                not prompt or 
                len(prompt.strip()) < 3
            )
        ):
            st.session_state.processing = True
            
            with st.spinner("🔄 Генерация... (30-60 секунд)"):
                
                # Подготавливаем данные
                images_data = [img["data"] for img in st.session_state.uploaded_images]
                
                # Отправляем запрос
                gen_result = st.session_state.generator.generate_multi_image(prompt, images_data)
                
                if gen_result and "error" not in gen_result:
                    if 'data' in gen_result and 'task_id' in gen_result['data']:
                        task_id = gen_result['data']['task_id']
                        
                        # Получаем результат
                        image_url = st.session_state.generator.get_task_result(task_id)
                        
                        if image_url:
                            st.session_state.last_result = image_url
                            st.success("✅ Готово!")
                            st.rerun()
                        else:
                            st.error("❌ Не удалось получить результат")
                    else:
                        st.error("❌ Ошибка API")
                else:
                    error_msg = gen_result.get("error", "Неизвестная ошибка") if gen_result else "Ошибка"
                    st.error(f"❌ {error_msg}")
            
            st.session_state.processing = False
        
        # Отображение результата
        if st.session_state.last_result:
            st.subheader("🎨 Результат")
            st.image(st.session_state.last_result, use_column_width=True)
            st.markdown(f"[📥 Скачать]({st.session_state.last_result})")

if __name__ == "__main__":
    main()
