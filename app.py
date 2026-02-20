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
import traceback

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация API
API_KEY = "dk-13a00e5103d9345a25a6df802988ad47"
API_URL_GEN = "https://api.defapi.org/api/image/gen"
API_URL_QUERY = "https://api.defapi.org/api/task/query"

@st.cache_data(ttl=3600, show_spinner=False)
def safe_process_image(image_bytes: bytes) -> Optional[dict]:
    """Безопасная обработка любого изображения с множественными попытками"""
    
    results = []
    errors = []
    
    # Пробуем разные методы обработки
    methods = [
        {"name": "Метод 1: Оригинал -> JPEG", "quality": 95, "max_size": None},
        {"name": "Метод 2: Сжатие 1024px", "quality": 85, "max_size": 1024},
        {"name": "Метод 3: Сильное сжатие", "quality": 75, "max_size": 768},
        {"name": "Метод 4: Минимальное", "quality": 65, "max_size": 512},
    ]
    
    for method in methods:
        try:
            # Открываем изображение
            img = Image.open(io.BytesIO(image_bytes))
            
            # Конвертируем в RGB если нужно
            if img.mode in ('RGBA', 'LA', 'P'):
                # Для прозрачных изображений делаем белый фон
                if img.mode == 'RGBA':
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[3])
                    img = background
                else:
                    img = img.convert('RGB')
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Изменяем размер если нужно
            if method["max_size"] and max(img.size) > method["max_size"]:
                ratio = method["max_size"] / max(img.size)
                new_size = tuple(int(dim * ratio) for dim in img.size)
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            # Сохраняем с разными параметрами
            buffer = io.BytesIO()
            
            # Пробуем сохранить как JPEG
            try:
                img.save(buffer, format='JPEG', quality=method["quality"], optimize=True)
            except:
                # Если не получается, пробуем без оптимизации
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=method["quality"])
            
            compressed_bytes = buffer.getvalue()
            
            # Конвертируем в base64
            base64_image = base64.b64encode(compressed_bytes).decode('utf-8')
            
            # Проверяем размер
            if len(base64_image) < 5 * 1024 * 1024:  # Меньше 5MB
                image_hash = hashlib.md5(compressed_bytes).hexdigest()[:8]
                
                return {
                    "data": base64_image,
                    "mime_type": "image/jpeg",
                    "hash": image_hash,
                    "method": method["name"],
                    "original_size": len(image_bytes),
                    "processed_size": len(compressed_bytes)
                }
            else:
                errors.append(f"{method['name']}: слишком большой результат ({len(base64_image)/1024/1024:.1f}MB)")
                
        except Exception as e:
            errors.append(f"{method['name']}: {str(e)}")
            continue
    
    # Если ничего не получилось, логируем ошибки
    logger.error(f"Все методы обработки не удались: {errors}")
    return None

class ImageGenerator:
    def __init__(self):
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        }
    
    def generate_multi_image(self, prompt: str, images_data: List[dict]) -> dict:
        """Генерирует изображение с автоматическим выбором метода"""
        
        if not images_data:
            return {"error": "Нет изображений"}
        
        # Подготавливаем изображения - пробуем разные форматы
        results = []
        
        # Формат 1: images как массив с data URL
        try:
            processed_images = []
            for img_data in images_data:
                data_url = f"data:{img_data['mime_type']};base64,{img_data['data']}"
                processed_images.append(data_url)
            
            data = {
                "model": "google/nano-banana",
                "prompt": prompt,
                "images": processed_images
            }
            
            response = requests.post(
                API_URL_GEN,
                headers=self.headers,
                json=data,
                timeout=60
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                results.append({"format": "data_url", "status": response.status_code})
        except Exception as e:
            results.append({"format": "data_url", "error": str(e)})
        
        # Формат 2: без префикса data:
        try:
            processed_images = [img['data'] for img in images_data]
            
            data = {
                "model": "google/nano-banana",
                "prompt": prompt,
                "images": processed_images
            }
            
            response = requests.post(
                API_URL_GEN,
                headers=self.headers,
                json=data,
                timeout=60
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                results.append({"format": "raw_base64", "status": response.status_code})
        except Exception as e:
            results.append({"format": "raw_base64", "error": str(e)})
        
        # Формат 3: image_url вместо images
        if len(images_data) == 1:
            try:
                data = {
                    "model": "google/nano-banana",
                    "prompt": prompt,
                    "image_url": f"data:{images_data[0]['mime_type']};base64,{images_data[0]['data']}"
                }
                
                response = requests.post(
                    API_URL_GEN,
                    headers=self.headers,
                    json=data,
                    timeout=60
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    results.append({"format": "image_url", "status": response.status_code})
            except Exception as e:
                results.append({"format": "image_url", "error": str(e)})
        
        return {
            "error": "Все форматы запроса не удались",
            "details": results
        }
    
    def get_task_result(self, task_id: str) -> Optional[str]:
        """Получает результат задачи"""
        try:
            url = f"{API_URL_QUERY}?task_id={task_id}"
            
            for attempt in range(30):
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
                                if isinstance(data['result'], list):
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
    if 'debug_info' not in st.session_state:
        st.session_state.debug_info = None

def clear_all():
    st.session_state.uploaded_images = []
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
    
    st.title("🎨 Универсальный генератор изображений")
    st.markdown("---")
    
    # Debug секция
    with st.expander("🔧 Информация об изображениях", expanded=False):
        if st.session_state.uploaded_images:
            for i, img in enumerate(st.session_state.uploaded_images):
                st.write(f"**Изображение {i+1}:**")
                st.write(f"- Метод обработки: {img.get('method', 'N/A')}")
                st.write(f"- Оригинальный размер: {img.get('original_size', 0)/1024:.1f}KB")
                st.write(f"- Обработанный размер: {img.get('processed_size', 0)/1024:.1f}KB")
                st.write(f"- Хеш: {img.get('hash', 'N/A')}")
        
        if st.session_state.debug_info:
            st.json(st.session_state.debug_info)
    
    with st.sidebar:
        st.header("ℹ️ Информация")
        st.markdown("""
        **Как это работает:**
        1. Загрузите до 4 изображений (любые форматы)
        2. Напишите промпт
        3. Нажмите "Сгенерировать"
        
        **Поддерживаются:** JPG, PNG, GIF, WEBP, BMP
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
            type=['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'],
            accept_multiple_files=True,
            key="file_uploader",
            disabled=st.session_state.processing
        )
        
        if uploaded_files and not st.session_state.processing:
            new_images = []
            
            for uploaded_file in uploaded_files:
                try:
                    if len(st.session_state.uploaded_images) + len(new_images) >= 4:
                        st.warning("Максимум 4 изображения")
                        break
                    
                    bytes_data = uploaded_file.getvalue()
                    
                    with st.spinner(f"Обработка {uploaded_file.name}..."):
                        processed = safe_process_image(bytes_data)
                    
                    if processed:
                        new_images.append({
                            "data": processed,
                            "name": uploaded_file.name,
                            "thumbnail": bytes_data,
                            "method": processed.get("method", "Unknown"),
                            "original_size": processed.get("original_size", 0),
                            "processed_size": processed.get("processed_size", 0),
                            "hash": processed.get("hash", "")
                        })
                        st.success(f"✅ {uploaded_file.name} - {processed.get('method', 'OK')}")
                    else:
                        st.error(f"❌ Не удалось обработать {uploaded_file.name}")
                    
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
                
                # Сохраняем debug информацию
                st.session_state.debug_info = {
                    "prompt": prompt,
                    "num_images": len(images_data),
                    "image_methods": [img.get("method", "Unknown") for img in st.session_state.uploaded_images]
                }
                
                status_text.text("Отправка запроса к API...")
                progress_bar.progress(20)
                
                gen_result = st.session_state.generator.generate_multi_image(prompt, images_data)
                
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
                        st.session_state.error_message = f"Неверный ответ от API"
                else:
                    error_msg = gen_result.get("error", "Неизвестная ошибка")
                    details = gen_result.get("details", [])
                    st.session_state.error_message = f"Ошибка: {error_msg}"
                    st.session_state.debug_info["error_details"] = details
                    
            except Exception as e:
                st.session_state.error_message = f"Ошибка: {str(e)}"
                st.session_state.debug_info["exception"] = traceback.format_exc()
            
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
