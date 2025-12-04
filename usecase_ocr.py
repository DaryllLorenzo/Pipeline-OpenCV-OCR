import easyocr
import cv2
import numpy as np
from typing import List, Tuple, Dict, Optional
import json
import re
from collections import defaultdict

class UseCaseOCR:
    def __init__(self, image_path: str, actor_blacklist: List[str] = None, 
                 languages: List[str] = ['es', 'en'], gpu: bool = False):
        """
        Inicializa el lector OCR para detectar casos de uso en diagramas.
        
        Args:
            image_path: Ruta de la imagen del diagrama
            actor_blacklist: Lista de nombres de actores para excluir del OCR
            languages: Idiomas para OCR
            gpu: Usar GPU para OCR (False para CPU)
        """
        self.image_path = image_path
        self.reader = easyocr.Reader(languages, gpu=gpu)
        self.results = None
        self.image = cv2.imread(image_path)
        if self.image is None:
            raise ValueError(f"No se pudo cargar la imagen: {image_path}")
        
        self.image_rgb = cv2.cvtColor(self.image, cv2.COLOR_BGR2RGB)
        self.height, self.width = self.image.shape[:2]
        
        # Lista negra de textos de actores para excluir del OCR
        self.actor_blacklist = []
        if actor_blacklist:
            self.actor_blacklist = [text.lower().strip() for text in actor_blacklist if text.strip()]
        
        # Resultados filtrados (sin actores)
        self.filtered_results = []
        self.use_cases = []
        self.debug = False  # Flag para modo debug

    def add_actor_blacklist(self, actor_texts: List[str]):
        """
        Agrega textos de actores a la lista negra para excluir del OCR.
        
        Args:
            actor_texts: Lista de nombres de actores detectados
        """
        for text in actor_texts:
            if text and text.strip():
                self.actor_blacklist.append(text.lower().strip())

    def is_actor_text(self, text: str) -> bool:
        """
        Verifica si el texto pertenece a un actor (está en la blacklist)
        o contiene palabras clave de relaciones UML.
        
        Args:
            text: Texto a verificar
            
        Returns:
            bool: True si es texto de actor o relación UML
        """
        text_lower = text.lower().strip()
        
        # 1. Verificar si está en la blacklist de actores
        if self.actor_blacklist:
            for actor_text in self.actor_blacklist:
                actor_text_lower = actor_text.lower()
                # Verificar coincidencia exacta o parcial
                if (actor_text_lower == text_lower or 
                    actor_text_lower in text_lower or 
                    text_lower in actor_text_lower):
                    return True
        
        # 2. Verificar si contiene palabras clave de relaciones UML
        # Limpiar texto de caracteres especiales para mejor matching
        text_clean = text_lower.replace('<<', '').replace('>>', '').strip()
        
        uml_relations = [
            'include', 'extend', 'includes', 'extends',
            'includ', 'extend'  # Para capturar variaciones
        ]
        
        # Verificar si alguna relación UML está en el texto
        for relation in uml_relations:
            if relation in text_clean:
                return True
        
        # 3. Verificar patrones específicos de UML
        # Patrones para <<include>>, <<extend>>, etc.
        uml_patterns = [
            r'<<\s*include\s*>>',
            r'<<\s*extend\s*>>',
            r'<<\s*includes?\s*>>?',
            r'<<\s*extends?\s*>>?',
            r'include\s*>>',
            r'extend\s*>>',
            r'<<\s*include',
            r'<<\s*extend',
            r'tend'
        ]
        
        for pattern in uml_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True
        
        # 4. Verificar si el texto parece ser una flecha/relación UML
        arrow_patterns = ['->', '-->', '>>', '<<']
        for arrow in arrow_patterns:
            if arrow in text:
                # Si tiene flecha y también palabras relacionadas
                if any(word in text_lower for word in ['include', 'extend']):
                    return True
        
        return False

    def _expand_bbox(self, bbox, expand_x=30, expand_y=25):
        """
        Expande un bounding box en todas las direcciones.
        
        Args:
            bbox: Bounding box original (4 puntos)
            expand_x: Píxeles a expandir horizontalmente
            expand_y: Píxeles a expandir verticalmente
            
        Returns:
            Bounding box expandido
        """
        # Extraer coordenadas
        x_coords = [point[0] for point in bbox]
        y_coords = [point[1] for point in bbox]
        
        x_min = max(0, min(x_coords) - expand_x)
        y_min = max(0, min(y_coords) - expand_y)
        x_max = min(self.width, max(x_coords) + expand_x)
        y_max = min(self.height, max(y_coords) + expand_y)
        
        # Crear nuevo bounding box expandido
        expanded_bbox = [
            [x_min, y_min],
            [x_max, y_min],
            [x_max, y_max],
            [x_min, y_max]
        ]
        
        return expanded_bbox

    def _calculate_iou(self, bbox1, bbox2):
        """
        Calcula el Intersection over Union (IoU) entre dos bounding boxes.
        
        Args:
            bbox1: Primer bounding box
            bbox2: Segundo bounding box
            
        Returns:
            float: Valor IoU (0-1)
        """
        # Convertir a coordenadas rectangulares
        x1_1, y1_1 = bbox1[0]
        x2_1, y2_1 = bbox1[2]
        x1_2, y1_2 = bbox2[0]
        x2_2, y2_2 = bbox2[2]
        
        # Calcular intersección
        x_left = max(x1_1, x1_2)
        y_top = max(y1_1, y1_2)
        x_right = min(x2_1, x2_2)
        y_bottom = min(y2_1, y2_2)
        
        if x_right < x_left or y_bottom < y_top:
            return 0.0
        
        intersection_area = (x_right - x_left) * (y_bottom - y_top)
        
        # Calcular áreas individuales
        area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
        area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
        
        # Calcular unión
        union_area = area1 + area2 - intersection_area
        
        return intersection_area / union_area if union_area > 0 else 0.0

    def _should_merge_texts(self, text1, text2):
        """
        Determina si dos textos deberían fusionarse.
        
        Args:
            text1: Primer texto
            text2: Segundo texto
            
        Returns:
            bool: True si deberían fusionarse
        """
        # Convertir a minúsculas para comparación
        t1 = text1.lower().strip()
        t2 = text2.lower().strip()
        
        # Si uno está completamente contenido en el otro
        if t1 in t2 or t2 in t1:
            return True
        
        # Si ambos parecen ser parte del mismo caso de uso
        # (ej: "44" y "Eliminar tipo de fuente")
        if t1.isdigit() and not t2.isdigit():
            return True
        if t2.isdigit() and not t1.isdigit():
            return True
        
        # Si ambos son números consecutivos (ej: "44" y "45")
        if t1.isdigit() and t2.isdigit():
            num1 = int(t1)
            num2 = int(t2)
            if abs(num1 - num2) <= 2:  # Números consecutivos o cercanos
                return True
        
        # Si comparten palabras comunes significativas
        words1 = set(t1.split())
        words2 = set(t2.split())
        common_words = words1.intersection(words2)
        
        # Si tienen al menos una palabra común de más de 3 letras
        if any(len(word) > 3 for word in common_words):
            return True
        
        # Si juntos forman un texto más coherente
        #combined = f"{text1} {text2}".lower()
        ## Verificar si parece un caso de uso típico
        #use_case_keywords = ['crear', 'editar', 'eliminar', 'consultar', 
        #                    'listar', 'buscar', 'filtrar', 'exportar',
        #                    'importar', 'validar', 'aprobar', 'rechazar']
        #
        #if any(keyword in combined for keyword in use_case_keywords):
        #    return True
        
        return False

    def _merge_similar_boxes(self, results, iou_threshold=0.3):
        """
        Fusiona bounding boxes que están muy cerca y tienen textos relacionados.
        
        Args:
            results: Lista de resultados OCR
            iou_threshold: Umbral de IoU para considerar superposición
            
        Returns:
            Lista de resultados fusionados
        """
        if not results:
            return []
        
        # Preparar datos
        for idx, result in enumerate(results):
            result['id'] = idx
            bbox = result['bbox']
            x_coords = [point[0] for point in bbox]
            y_coords = [point[1] for point in bbox]
            result['x_min'] = min(x_coords)
            result['y_min'] = min(y_coords)
            result['x_max'] = max(x_coords)
            result['y_max'] = max(y_coords)
            result['center_x'] = (result['x_min'] + result['x_max']) / 2
            result['center_y'] = (result['y_min'] + result['y_max']) / 2
        
        # Ordenar por posición horizontal y vertical
        results.sort(key=lambda x: (x['y_min'], x['x_min']))
        
        # Crear lista de grupos
        groups = []
        used_ids = set()
        
        for i in range(len(results)):
            if i in used_ids:
                continue
                
            current_group = [results[i]]
            used_ids.add(i)
            
            for j in range(i + 1, len(results)):
                if j in used_ids:
                    continue
                    
                # Calcular IoU
                iou = self._calculate_iou(results[i]['bbox'], results[j]['bbox'])
                
                # Calcular distancia vertical
                vertical_distance = abs(results[i]['center_y'] - results[j]['center_y'])
                
                # Calcular distancia horizontal
                horizontal_gap = max(0, results[j]['x_min'] - results[i]['x_max'])
                
                # Verificar si deberían estar juntos
                should_merge = False
                
                # Si tienen buena superposición
                if iou > iou_threshold:
                    should_merge = True
                
                # Si están en la misma línea y cerca horizontalmente
                elif vertical_distance < 15 and horizontal_gap < 100:
                    # Verificar si los textos están relacionados
                    if self._should_merge_texts(results[i]['text'], results[j]['text']):
                        should_merge = True
                
                if should_merge:
                    current_group.append(results[j])
                    used_ids.add(j)
            
            if current_group:
                groups.append(current_group)
        
        # Fusionar grupos
        merged_results = []
        
        for group in groups:
            if len(group) == 1:
                # Mantener el resultado original
                merged_results.append(group[0])
            else:
                # Fusionar múltiples resultados
                x_mins = [r['x_min'] for r in group]
                y_mins = [r['y_min'] for r in group]
                x_maxs = [r['x_max'] for r in group]
                y_maxs = [r['y_max'] for r in group]
                
                # Ordenar por posición horizontal
                sorted_group = sorted(group, key=lambda x: x['x_min'])
                
                # Combinar textos (mantener orden original)
                combined_text = ' '.join([r['text'] for r in sorted_group])
                
                # Calcular confianza promedio
                avg_confidence = sum(r['confidence'] for r in group) / len(group)
                
                # Crear nuevo bounding box que cubra todos
                merged_bbox = [
                    [min(x_mins), min(y_mins)],
                    [max(x_maxs), min(y_mins)],
                    [max(x_maxs), max(y_maxs)],
                    [min(x_mins), max(y_maxs)]
                ]
                
                merged_result = {
                    'bbox': merged_bbox,
                    'text': combined_text,
                    'confidence': avg_confidence,
                    'x_min': min(x_mins),
                    'y_min': min(y_mins),
                    'x_max': max(x_maxs),
                    'y_max': max(y_maxs),
                    'merged_from': len(group)  # Cuántos boxes se fusionaron
                }
                merged_results.append(merged_result)
        
        return merged_results

    def _remove_duplicate_cases(self, results, similarity_threshold=0.8):
        """
        Elimina casos de uso duplicados o muy similares.
        
        Args:
            results: Lista de resultados OCR
            similarity_threshold: Umbral de similitud para considerar duplicado
            
        Returns:
            Lista de resultados sin duplicados
        """
        if not results:
            return []
        
        # Función para calcular similitud entre textos
        def text_similarity(text1, text2):
            text1_lower = text1.lower().strip()
            text2_lower = text2.lower().strip()
            
            # Si uno está contenido en el otro
            if text1_lower in text2_lower or text2_lower in text1_lower:
                return 1.0
            
            # Calcular similitud basada en palabras comunes
            words1 = set(text1_lower.split())
            words2 = set(text2_lower.split())
            
            if not words1 or not words2:
                return 0.0
            
            intersection = words1.intersection(words2)
            union = words1.union(words2)
            
            return len(intersection) / len(union)
        
        # Ordenar por confianza descendente
        results.sort(key=lambda x: x['confidence'], reverse=True)
        
        unique_results = []
        for result in results:
            is_duplicate = False
            
            for unique in unique_results:
                # Verificar similitud de texto
                similarity = text_similarity(result['text'], unique['text'])
                
                # Verificar superposición espacial usando IoU
                iou = self._calculate_iou(result['bbox'], unique['bbox'])
                
                # Si son muy similares en texto o tienen mucha superposición
                if similarity > similarity_threshold or iou > 0.5:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique_results.append(result)
        
        return unique_results

    def _draw_initial_results(self, output_path="debug_1_initial_ocr.png"):
        """Dibuja los resultados OCR iniciales antes de cualquier procesamiento."""
        if not self.results:
            return
        
        debug_image = self.image_rgb.copy()
        
        for bbox, text, confidence in self.results:
            # Convertir bbox a puntos enteros
            points = np.array(bbox, dtype=np.int32)
            
            # Dibujar bbox original (rojo)
            cv2.polylines(debug_image, [points], isClosed=True, 
                         color=(255, 0, 0), thickness=1)
            
            # Calcular posición para el texto
            min_x = min(points[:, 0])
            min_y = min(points[:, 1])
            
            # Dibujar texto con confianza
            display_text = f"{text[:20]} ({confidence:.2f})"
            cv2.putText(
                debug_image,
                display_text,
                (min_x, min_y - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (255, 0, 0),
                1,
                cv2.LINE_AA
            )
        
        # Guardar imagen
        cv2.imwrite(output_path, cv2.cvtColor(debug_image, cv2.COLOR_RGB2BGR))
        print(f"Debug 1: Bounding boxes iniciales -> {output_path}")

    def _draw_expanded_boxes(self, results, output_path="debug_2_expanded_boxes.png"):
        """Dibuja los bounding boxes expandidos."""
        if not results:
            return
        
        debug_image = self.image_rgb.copy()
        
        for result in results:
            bbox = result['bbox']
            original_bbox = result.get('original_bbox', bbox)
            text = result['text']
            confidence = result['confidence']
            
            # Convertir puntos a enteros
            points_expanded = np.array(bbox, dtype=np.int32)
            points_original = np.array(original_bbox, dtype=np.int32)
            
            # Dibujar bbox original (rojo, delgado)
            cv2.polylines(debug_image, [points_original], isClosed=True, 
                         color=(255, 0, 0), thickness=1)
            
            # Dibujar bbox expandido (verde, grueso)
            cv2.polylines(debug_image, [points_expanded], isClosed=True, 
                         color=(0, 255, 0), thickness=2)
            
            # Calcular posición para el texto
            min_x = min(points_expanded[:, 0])
            min_y = min(points_expanded[:, 1])
            
            # Dibujar texto con confianza
            display_text = f"{text[:20]} ({confidence:.2f})"
            cv2.putText(
                debug_image,
                display_text,
                (min_x, min_y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (0, 255, 0),
                1,
                cv2.LINE_AA
            )
        
        # Guardar imagen
        cv2.imwrite(output_path, cv2.cvtColor(debug_image, cv2.COLOR_RGB2BGR))
        print(f"Debug 2: Bounding boxes expandidos -> {output_path}")

    def _draw_merged_boxes(self, results, output_path="debug_3_merged_boxes.png"):
        """Dibuja los bounding boxes después de la fusión."""
        if not results:
            return
        
        debug_image = self.image_rgb.copy()
        
        # Colores diferentes para mostrar fusiones
        colors = [
            (0, 255, 0),    # Verde
            (255, 165, 0),  # Naranja
            (0, 255, 255),  # Amarillo
            (255, 0, 255),  # Magenta
            (0, 0, 255),    # Azul
        ]
        
        for idx, result in enumerate(results):
            bbox = result['bbox']
            text = result['text']
            confidence = result['confidence']
            merged_count = result.get('merged_from', 1)
            
            # Convertir puntos a enteros
            points = np.array(bbox, dtype=np.int32)
            
            # Seleccionar color según el número de fusiones
            color_idx = min(merged_count - 1, len(colors) - 1)
            color = colors[color_idx]
            
            # Dibujar bbox fusionado
            thickness = 2 if merged_count == 1 else 3
            cv2.polylines(debug_image, [points], isClosed=True, 
                         color=color, thickness=thickness)
            
            # Calcular posición para el texto
            min_x = min(points[:, 0])
            min_y = min(points[:, 1])
            
            # Dibujar texto con información de fusión
            if merged_count > 1:
                display_text = f"M{merged_count}: {text[:15]} ({confidence:.2f})"
            else:
                display_text = f"{text[:15]} ({confidence:.2f})"
            
            cv2.putText(
                debug_image,
                display_text,
                (min_x, min_y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                color,
                1,
                cv2.LINE_AA
            )
        
        # Guardar imagen
        cv2.imwrite(output_path, cv2.cvtColor(debug_image, cv2.COLOR_RGB2BGR))
        print(f"Debug 3: Bounding boxes fusionados -> {output_path}")

    def _draw_final_results(self, output_path="debug_4_final_results.png"):
        """Dibuja los resultados finales (después de filtrar actores)."""
        if not self.filtered_results:
            return
        
        debug_image = self.image_rgb.copy()
        
        for idx, result in enumerate(self.filtered_results):
            bbox = result['bbox']
            text = result['text']
            confidence = result['confidence']
            
            # Convertir puntos a enteros
            points = np.array(bbox, dtype=np.int32)
            
            # Dibujar bbox final (azul)
            cv2.polylines(debug_image, [points], isClosed=True, 
                         color=(0, 0, 255), thickness=3)
            
            # Calcular posición para el texto
            min_x = min(points[:, 0])
            min_y = min(points[:, 1])
            
            # Dibujar texto con confianza y ID de caso de uso
            display_text = f"CU{idx+1}: {text[:30]}"
            cv2.putText(
                debug_image,
                display_text,
                (min_x, min_y - 15),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 0, 255),
                1,
                cv2.LINE_AA
            )
            
            # Dibujar confianza
            cv2.putText(
                debug_image,
                f"Conf: {confidence:.2f}",
                (min_x, min_y - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (0, 100, 255),
                1,
                cv2.LINE_AA
            )
        
        # Guardar imagen
        cv2.imwrite(output_path, cv2.cvtColor(debug_image, cv2.COLOR_RGB2BGR))
        print(f"Debug 4: Resultados finales -> {output_path}")

    def run_ocr(self, confidence_threshold: float = 0.3, debug: bool = False):
        """
        Ejecuta OCR sobre la imagen y filtra resultados excluyendo actores.
        
        Args:
            confidence_threshold: Umbral de confianza mínimo
            debug: Si True, guarda imágenes de debug en cada etapa
            
        Returns:
            List: Resultados filtrados de casos de uso
        """
        print("Ejecutando OCR para casos de uso...")
        self.debug = debug  # Guardar para uso en otros métodos
        
        # Ejecutar OCR en toda la imagen
        self.results = self.reader.readtext(self.image_path)
        
        # Si estamos en modo debug, crear imagen inicial
        if debug:
            self._draw_initial_results("debug_1_initial_ocr.png")
        
        # Procesar resultados
        processed_results = []
        
        for bbox, text, confidence in self.results:
            # Filtrar por confianza mínima
            if confidence < confidence_threshold:
                continue
                
            # Filtrar texto muy corto (probablemente ruido)
            if len(text.strip()) < 2:  # Reducido a 2 para capturar números como "44"
                continue
                
            # Expandir bounding box para capturar texto completo
            expanded_bbox = self._expand_bbox(bbox, expand_x=30, expand_y=25)
            
            processed_results.append({
                'bbox': expanded_bbox,
                'text': text.strip(),
                'confidence': float(confidence),
                'original_bbox': bbox  # Guardar bbox original para debug
            })
        
        # Si estamos en modo debug, guardar imagen con boxes expandidos
        if debug:
            self._draw_expanded_boxes(processed_results, "debug_2_expanded_boxes.png")
        
        # Fusionar boxes similares (solo los que realmente están relacionados)
        merged_results = self._merge_similar_boxes(processed_results, iou_threshold=0.2)
        
        # Si estamos en modo debug, guardar imagen con boxes fusionados
        if debug:
            self._draw_merged_boxes(merged_results, "debug_3_merged_boxes.png")
        
        # Eliminar duplicados
        unique_results = self._remove_duplicate_cases(merged_results, similarity_threshold=0.7)
        
        # Filtrar por blacklist de actores
        self.filtered_results = []
        self.use_cases = []
        
        for result in unique_results:
            # Filtrar si es texto de actor (usando blacklist)
            if self.is_actor_text(result['text']):
                continue
                
            # Agregar a resultados filtrados
            self.filtered_results.append({
                'bbox': result['bbox'],
                'text': result['text'],
                'confidence': result['confidence']
            })
            self.use_cases.append(result['text'])
            
        print(f"Casos de uso detectados: {len(self.use_cases)}")
        
        # Si estamos en modo debug, dibujar los bounding boxes finales
        if debug:
            self._draw_final_results("debug_4_final_results.png")
        
        return self.filtered_results

    def get_use_cases(self) -> List[str]:
        """
        Obtiene la lista de casos de uso detectados.
        
        Returns:
            List[str]: Lista de casos de uso
        """
        return self.use_cases

    def get_formatted_results(self) -> List[Dict]:
        """
        Obtiene resultados formateados.
        
        Returns:
            List[Dict]: Resultados con información detallada
        """
        return [
            {
                'id': idx + 1,
                'text': result['text'],
                'confidence': result['confidence'],
                'bbox': [(float(x), float(y)) for (x, y) in result['bbox']]
            }
            for idx, result in enumerate(self.filtered_results)
        ]

    def print_results(self):
        """
        Imprime los casos de uso detectados.
        """
        if not self.filtered_results:
            print("No se detectaron casos de uso.")
            return
            
        print("\n=== CASOS DE USO DETECTADOS ===")
        for idx, result in enumerate(self.filtered_results, 1):
            print(f"{idx}. {result['text']} (Confianza: {result['confidence']:.2f})")

    def save_results(self, output_path: str = "usecases_results.json"):
        """
        Guarda los resultados en formato JSON.
        
        Args:
            output_path: Ruta del archivo JSON
        """
        results = {
            'use_cases': self.get_formatted_results(),
            'total_count': len(self.use_cases),
            'actor_blacklist': self.actor_blacklist
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            
        print(f"Resultados guardados: {output_path}")


# Función de ejemplo para uso independiente
def main():
    import sys
    
    if len(sys.argv) < 2:
        print("Uso: python usecase_ocr.py <imagen> [actor1 actor2 ...] [--debug]")
        return
    
    image_path = sys.argv[1]
    debug = '--debug' in sys.argv
    
    # Filtrar argumentos para obtener solo los nombres de actores
    actor_texts = []
    for arg in sys.argv[2:]:
        if arg != '--debug':
            actor_texts.append(arg)
    
    # Crear instancia de OCR
    ocr = UseCaseOCR(image_path, actor_blacklist=actor_texts, gpu=False)
    
    # Ejecutar OCR con modo debug si está activado
    results = ocr.run_ocr(debug=debug)
    
    # Imprimir resultados
    ocr.print_results()
    
    # Guardar resultados
    ocr.save_results()


if __name__ == "__main__":
    main()