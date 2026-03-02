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

# Конфигурация API
API_KEY = "dk-13a00e5103d9345a25a6df802988ad47"  # Ваш API ключ
API_URL_GEN = "https://api.defapi.org/api/image/gen"
API_URL_QUERY = "https://api.defapi.org/api/task/query"

# Создаем папку для сохранения изображений
IMAGES_FOLDER = "generated_images"
os.makedirs(IMAGES_FOLDER, exist_ok=True)

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
                'WEBP': "image/webp"
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
            "model": "google/nano-banana-pro",
            "prompt": prompt,
            "images": processed_images
        }
        
        try:
            logger.info(f"Отправка multi-image запроса: {prompt} с {len(images_data)} изображениями")
            
            response = requests.post(
                API_URL_GEN, 
                headers=self.headers, 
                json=data, 
                timeout=60
            )
            
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
    
    def get_task_result(self, task_id: str, max_attempts: int = 30, wait_time: int = 3) -> Optional[str]:
        """Получает результат задачи по task_id"""
        try:
            url = f"{API_URL_QUERY}?task_id={task_id}"
            
            for attempt in range(max_attempts):
                time.sleep(wait_time)
                
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
                
                if attempt == max_attempts - 1:
                    return None
                    
        except Exception as e:
            logger.error(f"Ошибка при получении результата: {e}")
            return None
    
    def download_and_save_image(self, image_url: str) -> Optional[str]:
        """Скачивает изображение по URL и сохраняет локально"""
        try:
            # Скачиваем изображение
            response = requests.get(image_url, timeout=30)
            
            if response.status_code != 200:
                logger.error(f"Не удалось скачать изображение: {response.status_code}")
                return None
            
            # Генерируем уникальное имя файла
            filename = f"{uuid.uuid4()}.jpg"
            filepath = os.path.join(IMAGES_FOLDER, filename)
            
            # Сохраняем изображение
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            logger.info(f"Изображение сохранено: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Ошибка при скачивании изображения: {e}")
            return None

def main():
    """Основная функция Streamlit приложения"""
    
    # Настройка страницы
    st.set_page_config(
        page_title="Генератор изображений",
        page_icon="🎨",
        layout="wide"
    )
    
    # Заголовок
    st.title("🎨 Генератор изображений из изображений")
    st.markdown("---")
    
    # Инициализация генератора в session state
    if 'generator' not in st.session_state:
        st.session_state.generator = ImageGenerator()
    
    if 'uploaded_images' not in st.session_state:
        st.session_state.uploaded_images = []
    
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    
    if 'last_result' not in st.session_state:
        st.session_state.last_result = None
    
    if 'last_result_path' not in st.session_state:
        st.session_state.last_result_path = None
    
    # Боковая панель с информацией
    with st.sidebar:
        st.header("ℹ️ Информация")
        st.markdown("""
        **Как это работает:**
        1. Загрузите до 4 изображений
        2. Напишите промпт (описание желаемого результата)
        3. Нажмите "Сгенерировать"
        4. Подождите 30-60 секунд
        
        **Примеры промптов:**
        - "Объедините эти изображения в коллаж"
        - "Создайте новое изображение на основе этих картинок"
        - "Поместите все объекты на один фон"
        """)
        
        st.markdown("---")
        st.markdown("**Статус:**")
        st.info(f"Загружено изображений: {len(st.session_state.uploaded_images)}/4")
        
        # Кнопка очистки старых изображений
        if st.button("🗑️ Очистить кэш изображений", use_container_width=True):
            try:
                # Удаляем все файлы в папке images
                for filename in os.listdir(IMAGES_FOLDER):
                    filepath = os.path.join(IMAGES_FOLDER, filename)
                    if os.path.isfile(filepath):
                        os.remove(filepath)
                st.success("✅ Кэш очищен")
            except Exception as e:
                st.error(f"Ошибка при очистке: {e}")
    
    # Основная область
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📤 Загрузка изображений")
        
        # Загрузка файлов
        uploaded_files = st.file_uploader(
            "Выберите изображения (до 4 шт.)",
            type=['png', 'jpg', 'jpeg', 'gif', 'webp'],
            accept_multiple_files=True,
            key="file_uploader",
            disabled=st.session_state.processing
        )
        
        # Обработка загруженных файлов
        if uploaded_files and not st.session_state.processing:
            # Ограничиваем количество файлов
            if len(uploaded_files) > 4:
                st.warning("Можно загрузить не более 4 изображений. Первые 4 будут использованы.")
                uploaded_files = uploaded_files[:4]
            
            # Обрабатываем каждый файл
            st.session_state.uploaded_images = []
            progress_bar = st.progress(0)
            
            for i, uploaded_file in enumerate(uploaded_files):
                try:
                    # Читаем файл
                    bytes_data = uploaded_file.getvalue()
                    
                    # Обрабатываем изображение
                    processed = st.session_state.generator.process_image(bytes_data)
                    
                    if processed:
                        st.session_state.uploaded_images.append({
                            "data": processed,
                            "name": uploaded_file.name,
                            "thumbnail": bytes_data
                        })
                    
                    progress_bar.progress((i + 1) / len(uploaded_files))
                    
                except Exception as e:
                    st.error(f"Ошибка при обработке {uploaded_file.name}: {str(e)}")
            
            progress_bar.empty()
            
            if st.session_state.uploaded_images:
                st.success(f"✅ Загружено {len(st.session_state.uploaded_images)} изображений")
        
        # Отображение загруженных изображений
        if st.session_state.uploaded_images:
            st.subheader("🖼️ Загруженные изображения")
            
            # Создаем сетку для превью
            cols = st.columns(min(len(st.session_state.uploaded_images), 4))
            
            for idx, img_data in enumerate(st.session_state.uploaded_images):
                with cols[idx % 4]:
                    # Отображаем превью
                    st.image(
                        img_data["thumbnail"],
                        caption=img_data["name"][:15] + "..." if len(img_data["name"]) > 15 else img_data["name"],
                        use_column_width=True
                    )
            
            # Кнопка очистки
            if st.button("🗑️ Очистить все изображения", disabled=st.session_state.processing):
                st.session_state.uploaded_images = []
                st.rerun()
    
    with col2:
        st.subheader("📝 Промпт и генерация")
        
        # Поле для ввода промпта
        prompt = st.text_area(
            "Введите описание желаемого результата:",
            height=100,
            placeholder="Например: Объедините все изображения в один коллаж на фоне заката...",
            disabled=st.session_state.processing or len(st.session_state.uploaded_images) == 0
        )
        
        # Кнопка генерации
        generate_button = st.button(
            "🚀 Сгенерировать",
            type="primary",
            use_container_width=True,
            disabled=(
                st.session_state.processing or 
                len(st.session_state.uploaded_images) == 0 or 
                not prompt or 
                len(prompt.strip()) < 3
            )
        )
        
        # Область для результата
        result_placeholder = st.empty()
        
        # Обработка генерации
        if generate_button:
            st.session_state.processing = True
            
            try:
                # Подготавливаем данные для API
                images_data = [img["data"] for img in st.session_state.uploaded_images]
                
                # Показываем прогресс
                with st.spinner("🔄 Генерация изображения... Это может занять 30-60 секунд"):
                    
                    # Отправляем запрос на генерацию
                    gen_result = st.session_state.generator.generate_multi_image(prompt, images_data)
                    
                    if gen_result and "error" not in gen_result:
                        if 'data' in gen_result and 'task_id' in gen_result['data']:
                            task_id = gen_result['data']['task_id']
                            
                            # Получаем URL изображения
                            image_url = st.session_state.generator.get_task_result(task_id)
                            
                            if image_url:
                                # Скачиваем и сохраняем изображение локально
                                local_path = st.session_state.generator.download_and_save_image(image_url)
                                
                                if local_path:
                                    st.session_state.last_result_path = local_path
                                    
                                    # Отображаем результат из локального файла
                                    with result_placeholder.container():
                                        st.success("✅ Генерация завершена!")
                                        st.image(local_path, caption="Результат", use_column_width=True)
                                        
                                        # Кнопка для скачивания
                                        with open(local_path, "rb") as file:
                                            btn = st.download_button(
                                                label="📥 Скачать изображение",
                                                data=file,
                                                file_name=f"generated_{uuid.uuid4()}.jpg",
                                                mime="image/jpeg"
                                            )
                                else:
                                    st.error("❌ Не удалось сохранить изображение локально")
                            else:
                                st.error("❌ Не удалось получить результат генерации")
                        else:
                            st.error(f"❌ Ошибка API: {gen_result}")
                    else:
                        error_msg = gen_result.get("error", "Неизвестная ошибка") if gen_result else "Ошибка подключения"
                        st.error(f"❌ Ошибка при генерации: {error_msg}")
                
            except Exception as e:
                st.error(f"❌ Произошла ошибка: {str(e)}")
                logger.error(f"Ошибка генерации: {e}", exc_info=True)
            
            finally:
                st.session_state.processing = False
                st.rerun()
        
        # Если не в процессе генерации, показываем последний результат (если есть)
        elif not st.session_state.processing and st.session_state.last_result_path:
            if os.path.exists(st.session_state.last_result_path):
                with result_placeholder.container():
                    st.subheader("🎨 Последний результат")
                    st.image(st.session_state.last_result_path, caption="Результат", use_column_width=True)
                    
                    with open(st.session_state.last_result_path, "rb") as file:
                        btn = st.download_button(
                            label="📥 Скачать изображение",
                            data=file,
                            file_name=f"generated_{uuid.uuid4()}.jpg",
                            mime="image/jpeg"
                        )

if __name__ == "__main__":
    main()

