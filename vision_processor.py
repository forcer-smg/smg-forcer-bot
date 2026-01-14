# -*- coding: utf-8 -*-
"""
Vision Processor - Handles image processing using Hugging Face and OpenRouter
Provides image captioning, analysis, and conversion capabilities
"""

import os
import io
import base64
import logging
import time
from typing import Dict, Optional, Union, List
from pathlib import Path
import requests

logger = logging.getLogger(__name__)

try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    logger.warning("Pillow not available. Image processing will be limited.")


class VisionProcessor:
    """Processes images using multiple vision model providers"""
    
    def __init__(self, huggingface_key: Optional[str] = None, openrouter_key: Optional[str] = None,
                 google_api_key: Optional[str] = None, replicate_api_key: Optional[str] = None,
                 ocr_space_key: Optional[str] = None, mindee_key: Optional[str] = None,
                 elysia_key: Optional[str] = None):
        self.huggingface_key = huggingface_key or os.getenv('HUGGINGFACE_API_KEY')
        self.openrouter_key = openrouter_key or os.getenv('OPENROUTER_API_KEY')
        self.google_api_key = google_api_key or os.getenv('GOOGLE_API_KEY') or os.getenv('GOOGLE_GEMINI_API_KEY')
        self.replicate_api_key = replicate_api_key or os.getenv('REPLICATE_API_KEY')
        self.ocr_space_key = ocr_space_key or os.getenv('OCR_SPACE_API_KEY')  # Optional, has free tier without key
        self.mindee_key = mindee_key or os.getenv('MINDEE_API_KEY')  # FREE: 250 IDs/month
        self.elysia_key = elysia_key or os.getenv('ELYSIA_API_KEY')  # FREE API available
        
        self.hf_available = bool(self.huggingface_key)
        self.or_available = bool(self.openrouter_key)
        self.google_available = bool(self.google_api_key)
        self.replicate_available = bool(self.replicate_api_key)
        self.mindee_available = bool(self.mindee_key)
        self.elysia_available = bool(self.elysia_key)
        # OCR.space works without keys (free tier)
        
        # Check for local OCR libraries
        self.tesseract_available = self._check_tesseract()
        self.easyocr_available = self._check_easyocr()
        
        # Hugging Face models
        self.hf_models = {
            'caption': 'Salesforce/blip-image-captioning-base',
            'vqa': 'dandelin/vilt-b32-finetuned-vqa',
            'clip': 'openai/clip-vit-base-patch32'
        }
    
    def _check_tesseract(self) -> bool:
        """Check if Tesseract OCR is available (local, free)"""
        try:
            import pytesseract
            # Try to get version
            pytesseract.get_tesseract_version()
            return True
        except:
            return False
    
    def _check_easyocr(self) -> bool:
        """Check if EasyOCR is available (local, free)"""
        try:
            import easyocr
            return True
        except:
            return False
    
    def process_image_huggingface(self, image_data: Union[bytes, str, Path], 
                                   task: str = 'caption') -> Dict:
        """
        Process image using Hugging Face Inference API
        task: 'caption', 'vqa', or 'clip'
        """
        if not self.hf_available:
            raise ValueError("Hugging Face API key not configured")
        
        # Prepare image
        image_bytes = self._prepare_image(image_data)
        if not image_bytes:
            raise ValueError("Failed to prepare image data")
        
        # Select model
        model = self.hf_models.get(task, self.hf_models['caption'])
        
        # Hugging Face Inference API endpoint
        api_url = f"https://api-inference.huggingface.co/models/{model}"
        
        headers = {
            "Authorization": f"Bearer {self.huggingface_key}",
            "Content-Type": "application/octet-stream"
        }
        
        try:
            response = requests.post(api_url, headers=headers, data=image_bytes, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            # Format response based on task
            if task == 'caption':
                if isinstance(result, list) and len(result) > 0:
                    caption = result[0].get('generated_text', 'No caption generated')
                elif isinstance(result, dict):
                    caption = result.get('generated_text', str(result))
                else:
                    caption = str(result)
                
                return {
                    'success': True,
                    'provider': 'huggingface',
                    'task': task,
                    'result': caption,
                    'raw': result
                }
            else:
                return {
                    'success': True,
                    'provider': 'huggingface',
                    'task': task,
                    'result': result,
                    'raw': result
                }
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Hugging Face API error: {e}")
            return {
                'success': False,
                'provider': 'huggingface',
                'error': str(e)
            }
    
    def process_image_openrouter(self, image_data: Union[bytes, str, Path], 
                                 prompt: str = "What is in this image?") -> Dict:
        """
        Process image using OpenRouter API with vision models
        """
        if not self.or_available:
            raise ValueError("OpenRouter API key not configured")
        
        # Prepare image
        image_bytes = self._prepare_image(image_data)
        if not image_bytes:
            raise ValueError("Failed to prepare image data")
        
        # Convert to base64
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
        # OpenRouter API endpoint
        api_url = "https://openrouter.ai/api/v1/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {self.openrouter_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/forcer-smg/smg-forcer-bot",
            "X-Title": "SMG-Forcer-Bot"
        }
        
        # Try different vision models (fallback chain)
        vision_models = [
            "openai/gpt-4-vision-preview",
            "google/gemini-pro-vision",
            "anthropic/claude-3-opus",
            "anthropic/claude-3-sonnet"
        ]
        
        for model in vision_models:
            try:
                payload = {
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": prompt
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{image_base64}"
                                    }
                                }
                            ]
                        }
                    ],
                    "max_tokens": 1000
                }
                
                response = requests.post(api_url, headers=headers, json=payload, timeout=60)
                
                if response.status_code == 200:
                    result = response.json()
                    content = result['choices'][0]['message']['content']
                    
                    return {
                        'success': True,
                        'provider': 'openrouter',
                        'model': model,
                        'result': content,
                        'raw': result
                    }
                elif response.status_code == 404:
                    # Model not available, try next
                    continue
                else:
                    response.raise_for_status()
            
            except requests.exceptions.RequestException as e:
                logger.warning(f"OpenRouter model {model} failed: {e}")
                continue
        
        # All models failed
        return {
            'success': False,
            'provider': 'openrouter',
            'error': 'All vision models failed'
        }
    
    def process_image_google_gemini(self, image_data: Union[bytes, str, Path], 
                                     prompt: str = "What is in this image?") -> Dict:
        """
        Process image using Google Gemini API (FREE tier available)
        """
        if not self.google_available:
            raise ValueError("Google API key not configured")
        
        # Prepare image
        image_bytes = self._prepare_image(image_data)
        if not image_bytes:
            raise ValueError("Failed to prepare image data")
        
        # Convert to base64
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
        # Google Gemini API endpoint
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro-vision:generateContent?key={self.google_api_key}"
        
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": image_base64
                        }
                    }
                ]
            }]
        }
        
        try:
            response = requests.post(api_url, json=payload, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            content = result['candidates'][0]['content']['parts'][0]['text']
            
            return {
                'success': True,
                'provider': 'google_gemini',
                'result': content,
                'raw': result
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Google Gemini API error: {e}")
            return {
                'success': False,
                'provider': 'google_gemini',
                'error': str(e)
            }
    
    def process_image_replicate(self, image_data: Union[bytes, str, Path], 
                                prompt: str = "What is in this image?") -> Dict:
        """
        Process image using Replicate API (FREE tier available)
        Uses BLIP-2 model for image captioning
        """
        if not self.replicate_available:
            raise ValueError("Replicate API key not configured")
        
        # Prepare image
        image_bytes = self._prepare_image(image_data)
        if not image_bytes:
            raise ValueError("Failed to prepare image data")
        
        # Convert to base64 data URL
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        image_data_url = f"data:image/jpeg;base64,{image_base64}"
        
        # Replicate API endpoint
        api_url = "https://api.replicate.com/v1/predictions"
        
        headers = {
            "Authorization": f"Token {self.replicate_api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "version": "4b32258c42e9efd4288bb0840eaab4896285b5c29ee3e2057cc443d2fe2c8131",  # BLIP-2 model
            "input": {
                "image": image_data_url,
                "task": "image_captioning",
                "prompt": prompt
            }
        }
        
        try:
            # Create prediction
            response = requests.post(api_url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            
            prediction = response.json()
            prediction_id = prediction['id']
            
            # Poll for result
            result_url = f"https://api.replicate.com/v1/predictions/{prediction_id}"
            for _ in range(30):  # Max 30 seconds
                time.sleep(1)
                result_response = requests.get(result_url, headers=headers, timeout=10)
                result_response.raise_for_status()
                result_data = result_response.json()
                
                if result_data['status'] == 'succeeded':
                    caption = result_data['output']
                    return {
                        'success': True,
                        'provider': 'replicate',
                        'result': caption,
                        'raw': result_data
                    }
                elif result_data['status'] == 'failed':
                    raise Exception(f"Replicate prediction failed: {result_data.get('error', 'Unknown error')}")
            
            raise Exception("Replicate prediction timed out")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Replicate API error: {e}")
            return {
                'success': False,
                'provider': 'replicate',
                'error': str(e)
            }
    
    def process_image_ocr_space(self, image_data: Union[bytes, str, Path]) -> Dict:
        """
        Extract text from image using OCR.space API (FREE tier, no key required)
        """
        # Prepare image
        image_bytes = self._prepare_image(image_data)
        if not image_bytes:
            raise ValueError("Failed to prepare image data")
        
        # OCR.space API endpoint
        api_url = "https://api.ocr.space/parse/image"
        
        files = {
            'file': ('image.jpg', image_bytes, 'image/jpeg')
        }
        
        data = {
            'apikey': self.ocr_space_key or 'helloworld',  # Free tier key
            'language': 'eng',
            'isOverlayRequired': False
        }
        
        try:
            response = requests.post(api_url, files=files, data=data, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('ParsedResults') and len(result['ParsedResults']) > 0:
                extracted_text = result['ParsedResults'][0].get('ParsedText', '')
                return {
                    'success': True,
                    'provider': 'ocr_space',
                    'result': extracted_text,
                    'raw': result
                }
            else:
                return {
                    'success': False,
                    'provider': 'ocr_space',
                    'error': 'No text extracted'
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"OCR.space API error: {e}")
            return {
                'success': False,
                'provider': 'ocr_space',
                'error': str(e)
            }
    
    def process_image_mindee(self, image_data: Union[bytes, str, Path]) -> Dict:
        """
        Process ID document using Mindee API (FREE: 250 IDs/month, no credit card)
        Perfect for ID scanning and data extraction
        Get API key: https://mindee.com/product/international-id-ocr-api
        """
        if not self.mindee_available:
            raise ValueError("Mindee API key not configured")
        
        # Prepare image
        image_bytes = self._prepare_image(image_data)
        if not image_bytes:
            raise ValueError("Failed to prepare image data")
        
        # Mindee API endpoint for International ID OCR
        api_url = "https://api.mindee.net/v1/products/mindee/international_id/v1/predict"
        
        headers = {
            "Authorization": f"Token {self.mindee_key}"
        }
        
        files = {
            'document': ('id.jpg', image_bytes, 'image/jpeg')
        }
        
        try:
            response = requests.post(api_url, headers=headers, files=files, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('api_request', {}).get('status') == 'success':
                # Extract ID fields
                prediction = result.get('document', {}).get('inference', {}).get('prediction', {})
                
                extracted_data = {
                    'name': prediction.get('given_names', []) + prediction.get('surnames', []),
                    'date_of_birth': prediction.get('birth_date'),
                    'document_number': prediction.get('id_number'),
                    'document_type': prediction.get('document_type'),
                    'nationality': prediction.get('nationality'),
                    'gender': prediction.get('gender'),
                    'address': prediction.get('address'),
                    'expiry_date': prediction.get('expiry_date'),
                    'issuing_country': prediction.get('issuing_country')
                }
                
                return {
                    'success': True,
                    'provider': 'mindee',
                    'result': extracted_data,
                    'raw': result
                }
            else:
                return {
                    'success': False,
                    'provider': 'mindee',
                    'error': result.get('api_request', {}).get('error', {}).get('message', 'Unknown error')
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Mindee API error: {e}")
            return {
                'success': False,
                'provider': 'mindee',
                'error': str(e)
            }
    
    def process_image_elysia(self, image_data: Union[bytes, str, Path]) -> Dict:
        """
        Process ID card using Elysia Tools API (FREE API available)
        Extracts ID card data to JSON format
        Get API key: https://elysiatools.com/en/tools/ai-ocr-id-card-to-json
        API endpoint: https://elysiatools.com/en/api/tools/ai-ocr-id-card-to-json
        """
        if not self.elysia_available:
            raise ValueError("Elysia API key not configured")
        
        # Prepare image
        image_bytes = self._prepare_image(image_data)
        if not image_bytes:
            raise ValueError("Failed to prepare image data")
        
        # Convert to base64
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
        # Elysia Tools API endpoint (based on their API structure)
        # Try multiple possible endpoints
        api_endpoints = [
            "https://elysiatools.com/en/api/tools/ai-ocr-id-card-to-json",
            "https://api.elysiatools.com/v1/ocr/id-card",
            "https://elysiatools.com/api/tools/id-card-ocr"
        ]
        
        headers = {
            "Authorization": f"Bearer {self.elysia_key}",
            "Content-Type": "application/json",
            "X-API-Key": self.elysia_key  # Some APIs use X-API-Key header
        }
        
        payload = {
            "image": image_base64,
            "imageData": image_base64,  # Try different parameter names
            "format": "json",
            "outputFormat": "json"
        }
        
        # Try each endpoint
        for api_url in api_endpoints:
            try:
                response = requests.post(api_url, headers=headers, json=payload, timeout=30)
                
                if response.status_code == 200:
                    result = response.json()
                    
                    # Handle different response formats
                    if result.get('success') or result.get('status') == 'success':
                        return {
                            'success': True,
                            'provider': 'elysia',
                            'result': result.get('data', result.get('result', result)),
                            'raw': result
                        }
                    elif 'error' in result:
                        continue  # Try next endpoint
                    else:
                        # Assume success if we got 200
                        return {
                            'success': True,
                            'provider': 'elysia',
                            'result': result,
                            'raw': result
                        }
                elif response.status_code == 404:
                    continue  # Try next endpoint
                else:
                    response.raise_for_status()
                    
            except requests.exceptions.RequestException as e:
                logger.debug(f"Elysia endpoint {api_url} failed: {e}")
                continue
        
        # All endpoints failed
        logger.error("All Elysia API endpoints failed")
        return {
            'success': False,
            'provider': 'elysia',
            'error': 'All API endpoints failed. Please check API key and endpoint URL.'
        }
    
    def process_image_tesseract(self, image_data: Union[bytes, str, Path]) -> Dict:
        """
        Extract text from image using Tesseract OCR (LOCAL, FREE, no API key needed)
        Requires: pip install pytesseract
        System: apt-get install tesseract-ocr (Linux) or brew install tesseract (Mac)
        """
        if not self.tesseract_available:
            raise ValueError("Tesseract OCR not installed")
        
        try:
            import pytesseract
            from PIL import Image
            
            # Load image
            if isinstance(image_data, bytes):
                img = Image.open(io.BytesIO(image_data))
            elif isinstance(image_data, (str, Path)):
                img = Image.open(image_data)
            else:
                img = image_data
            
            # Extract text
            text = pytesseract.image_to_string(img)
            
            # Try to extract structured data (for IDs)
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            
            return {
                'success': True,
                'provider': 'tesseract',
                'result': text.strip(),
                'structured_data': data,
                'raw': {'text': text, 'data': data}
            }
            
        except Exception as e:
            logger.error(f"Tesseract OCR error: {e}")
            return {
                'success': False,
                'provider': 'tesseract',
                'error': str(e)
            }
    
    def process_image_easyocr(self, image_data: Union[bytes, str, Path]) -> Dict:
        """
        Extract text from image using EasyOCR (LOCAL, FREE, no API key needed)
        Requires: pip install easyocr
        First run downloads models (~500MB), then works offline
        """
        if not self.easyocr_available:
            raise ValueError("EasyOCR not installed")
        
        try:
            import easyocr
            import numpy as np
            from PIL import Image
            
            # Initialize reader (first time downloads models)
            reader = easyocr.Reader(['en'], gpu=False)  # Use GPU if available
            
            # Load image
            if isinstance(image_data, bytes):
                img = Image.open(io.BytesIO(image_data))
            elif isinstance(image_data, (str, Path)):
                img = Image.open(image_data)
            else:
                img = image_data
            
            # Convert to numpy array
            img_array = np.array(img)
            
            # Extract text
            results = reader.readtext(img_array)
            
            # Format results
            text_lines = [result[1] for result in results]
            full_text = '\n'.join(text_lines)
            
            return {
                'success': True,
                'provider': 'easyocr',
                'result': full_text,
                'detailed_results': results,
                'raw': {'text': full_text, 'results': results}
            }
            
        except Exception as e:
            logger.error(f"EasyOCR error: {e}")
            return {
                'success': False,
                'provider': 'easyocr',
                'error': str(e)
            }
    
    def process_image_pixlab(self, image_data: Union[bytes, str, Path], 
                            task: str = 'docscan') -> Dict:
        """
        Process image using PixLab API (FREE tier available)
        Great for ID/document scanning
        task: 'docscan' (ID scanning), 'ocr', 'face_detect'
        """
        # Prepare image
        image_bytes = self._prepare_image(image_data)
        if not image_bytes:
            raise ValueError("Failed to prepare image data")
        
        # Convert to base64
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
        # PixLab API endpoint
        if task == 'docscan':
            api_url = "https://api.pixlab.io/docscan"
        elif task == 'ocr':
            api_url = "https://api.pixlab.io/ocr"
        elif task == 'face_detect':
            api_url = "https://api.pixlab.io/facedetect"
        else:
            api_url = "https://api.pixlab.io/docscan"
        
        params = {
            'key': self.pixlab_key or 'free',  # Free tier
            'img': image_base64
        }
        
        try:
            response = requests.post(api_url, json=params, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('status') == 200:
                return {
                    'success': True,
                    'provider': 'pixlab',
                    'task': task,
                    'result': result.get('fields', result.get('text', result.get('faces', result))),
                    'raw': result
                }
            else:
                return {
                    'success': False,
                    'provider': 'pixlab',
                    'error': result.get('error', 'Unknown error')
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"PixLab API error: {e}")
            return {
                'success': False,
                'provider': 'pixlab',
                'error': str(e)
            }
    
    def process_image(self, image_data: Union[bytes, str, Path], 
                     task: str = 'caption',
                     prompt: Optional[str] = None,
                     prefer_provider: str = 'auto') -> Dict:
        """
        Process image using best available provider
        prefer_provider: 'auto', 'openrouter', 'google', 'replicate', 'huggingface', 'ocr', 'pixlab'
        """
        # Auto-select best provider based on availability
        if prefer_provider == 'auto':
            # Try free ID scanning APIs first (best for ID generation)
            if self.mindee_available and task in ['docscan', 'id', 'caption']:
                try:
                    result = self.process_image_mindee(image_data)
                    if result.get('success'):
                        return result
                except Exception as e:
                    logger.warning(f"Mindee failed: {e}")
            
            if self.elysia_available and task in ['docscan', 'id', 'caption']:
                try:
                    result = self.process_image_elysia(image_data)
                    if result.get('success'):
                        return result
                except Exception as e:
                    logger.warning(f"Elysia failed: {e}")
            
            # Try local OCR (free, no API key)
            if self.easyocr_available:
                try:
                    result = self.process_image_easyocr(image_data)
                    if result.get('success'):
                        return result
                except Exception as e:
                    logger.warning(f"EasyOCR failed: {e}")
            
            if self.tesseract_available:
                try:
                    result = self.process_image_tesseract(image_data)
                    if result.get('success'):
                        return result
                except Exception as e:
                    logger.warning(f"Tesseract failed: {e}")
            
            # Try free vision providers
            if self.google_available:
                try:
                    result = self.process_image_google_gemini(
                        image_data, 
                        prompt or "Describe this image in detail."
                    )
                    if result.get('success'):
                        return result
                except Exception as e:
                    logger.warning(f"Google Gemini failed: {e}")
            
            if self.replicate_available:
                try:
                    result = self.process_image_replicate(
                        image_data, 
                        prompt or "What is in this image?"
                    )
                    if result.get('success'):
                        return result
                except Exception as e:
                    logger.warning(f"Replicate failed: {e}")
            
            # Try OpenRouter
            if self.or_available:
                try:
                    result = self.process_image_openrouter(
                        image_data, 
                        prompt or "Describe this image in detail."
                    )
                    if result.get('success'):
                        return result
                except Exception as e:
                    logger.warning(f"OpenRouter failed: {e}")
            
            # Fallback to Hugging Face
            if self.hf_available:
                try:
                    result = self.process_image_huggingface(image_data, task)
                    if result.get('success'):
                        return result
                except Exception as e:
                    logger.warning(f"Hugging Face failed: {e}")
            
            # Try OCR.space (no key required)
            try:
                result = self.process_image_ocr_space(image_data)
                if result.get('success'):
                    return result
            except Exception as e:
                logger.warning(f"OCR.space failed: {e}")
        else:
            # Use specified provider
            if prefer_provider == 'mindee' and self.mindee_available:
                return self.process_image_mindee(image_data)
            elif prefer_provider == 'elysia' and self.elysia_available:
                return self.process_image_elysia(image_data)
            elif prefer_provider == 'easyocr' and self.easyocr_available:
                return self.process_image_easyocr(image_data)
            elif prefer_provider == 'tesseract' and self.tesseract_available:
                return self.process_image_tesseract(image_data)
            elif prefer_provider == 'google' and self.google_available:
                return self.process_image_google_gemini(image_data, prompt or "Describe this image in detail.")
            elif prefer_provider == 'replicate' and self.replicate_available:
                return self.process_image_replicate(image_data, prompt or "What is in this image?")
            elif prefer_provider == 'openrouter' and self.or_available:
                return self.process_image_openrouter(image_data, prompt or "Describe this image in detail.")
            elif prefer_provider == 'huggingface' and self.hf_available:
                return self.process_image_huggingface(image_data, task)
            elif prefer_provider == 'ocr':
                return self.process_image_ocr_space(image_data)
            elif prefer_provider == 'pixlab':
                return self.process_image_pixlab(image_data, task)
        
        # All failed
        return {
            'success': False,
            'error': 'No vision models available or all failed'
        }
    
    def _prepare_image(self, image_data: Union[bytes, str, Path]) -> Optional[bytes]:
        """Prepare image data for API requests"""
        try:
            # If it's already bytes
            if isinstance(image_data, bytes):
                return image_data
            
            # If it's a file path
            if isinstance(image_data, (str, Path)):
                path = Path(image_data)
                if path.exists():
                    return path.read_bytes()
                # Maybe it's a URL?
                if str(image_data).startswith(('http://', 'https://')):
                    response = requests.get(str(image_data), timeout=10)
                    response.raise_for_status()
                    return response.content
            
            # If it's a PIL Image
            if PILLOW_AVAILABLE and hasattr(image_data, 'save'):
                img_io = io.BytesIO()
                image_data.save(img_io, format='JPEG')
                return img_io.getvalue()
            
            return None
        
        except Exception as e:
            logger.error(f"Failed to prepare image: {e}")
            return None
    
    def convert_image(self, image_data: Union[bytes, str, Path], 
                     format: str = 'png',
                     resize: Optional[tuple] = None) -> Optional[bytes]:
        """
        Convert image format and optionally resize
        Returns converted image as bytes
        """
        if not PILLOW_AVAILABLE:
            logger.warning("Pillow not available for image conversion")
            return None
        
        try:
            # Load image
            if isinstance(image_data, bytes):
                img = Image.open(io.BytesIO(image_data))
            elif isinstance(image_data, (str, Path)):
                img = Image.open(image_data)
            else:
                img = image_data
            
            # Resize if requested
            if resize:
                img = img.resize(resize, Image.Resampling.LANCZOS)
            
            # Convert format
            output = io.BytesIO()
            img.save(output, format=format.upper())
            return output.getvalue()
        
        except Exception as e:
            logger.error(f"Image conversion failed: {e}")
            return None
    
    def analyze_screenshot(self, image_data: Union[bytes, str, Path]) -> Dict:
        """Analyze screenshot and extract text/information"""
        prompt = """Analyze this screenshot in detail. Describe:
1. What application or website is shown
2. Any visible text content
3. UI elements and their states
4. Any errors or warnings
5. Overall context and purpose"""
        
        return self.process_image(image_data, prompt=prompt)


# Global processor instance
_processor_instance = None

def get_vision_processor(hf_key: Optional[str] = None, or_key: Optional[str] = None,
                        google_key: Optional[str] = None, replicate_key: Optional[str] = None,
                        ocr_key: Optional[str] = None, mindee_key: Optional[str] = None,
                        elysia_key: Optional[str] = None) -> VisionProcessor:
    """Get or create global vision processor instance"""
    global _processor_instance
    if _processor_instance is None:
        _processor_instance = VisionProcessor(
            huggingface_key=hf_key,
            openrouter_key=or_key,
            google_api_key=google_key,
            replicate_api_key=replicate_key,
            ocr_space_key=ocr_key,
            mindee_key=mindee_key,
            elysia_key=elysia_key
        )
    return _processor_instance
