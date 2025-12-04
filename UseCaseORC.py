import easyocr
import cv2
import matplotlib.pyplot as plt

class UmlOCR:
    def __init__(self, image_path, languages=['es', 'en'], gpu=True):
        """
        Inicializa el lector OCR y carga la imagen.
        """
        self.image_path = image_path
        self.reader = easyocr.Reader(languages, gpu=gpu)
        self.results = None
        self.image_rgb = None

    def run_ocr(self):
        """
        Ejecuta OCR sobre la imagen y guarda los resultados.
        """
        self.results = self.reader.readtext(self.image_path)
        return self.results

    def print_results(self):
        """
        Imprime los textos detectados con su nivel de confianza.
        """
        if self.results is None:
            raise ValueError("Primero debes ejecutar run_ocr().")

        print("=== Resultados OCR ===")
        for bbox, text, confidence in self.results:
            print(f"Texto: {text} | Confianza: {confidence:.3f}")

    def draw_results(self):
        """
        Dibuja los bounding boxes y los textos detectados sobre la imagen.
        """
        if self.results is None:
            raise ValueError("Primero debes ejecutar run_ocr().")

        image = cv2.imread(self.image_path)
        self.image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        for bbox, text, confidence in self.results:
            (top_left, top_right, bottom_right, bottom_left) = bbox
            top_left = (int(top_left[0]), int(top_left[1]))
            bottom_right = (int(bottom_right[0]), int(bottom_right[1]))

            # Dibujar rectángulo
            cv2.rectangle(self.image_rgb, top_left, bottom_right, (0, 255, 0), 2)

            # Dibujar texto
            cv2.putText(
                self.image_rgb,
                text[:20],
                (top_left[0], top_left[1] - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (255, 0, 0),
                1,
                cv2.LINE_AA
            )

        plt.figure(figsize=(10, 8))
        plt.imshow(self.image_rgb)
        plt.axis("off")
        plt.show()


