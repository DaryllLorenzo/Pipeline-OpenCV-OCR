from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import tempfile
import os
import shutil
from datetime import datetime
from typing import List, Optional
import json

# Importar módulos personalizados
from actor_detector import DrawIOActorDetector
from usecase_ocr import UseCaseOCR
from pdf_builder import create_actors_pdf, create_compact_actors_pdf, create_simple_actors_pdf, filter_and_renumber_actors

app = FastAPI(
    title="Actor and Use Case Detection API",
    description="API para detección de actores y casos de uso en diagramas UML",
    version="2.0.0"
)

# Temporary directory for uploaded files
TEMP_DIR = "tmp"
os.makedirs(TEMP_DIR, exist_ok=True)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"], 
)

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Actor and Use Case Detection API",
        "endpoints": {
            "detect_actors": "POST /detect-actors/ - Upload image and detect actors & use cases",
            "detect_simple": "POST /detect-actors-simple/ - Simple detection with PDF output",
            "health": "GET /health/ - API health check",
            "example": "GET /example-actors/ - Example actors and use cases"
        },
        "version": "2.0.0"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.post("/detect-actors/")
async def detect_actors(
    file: UploadFile = File(..., description="Image file to process"),
    debug: bool = Query(False, description="Enable debug mode"),
    format: str = Query("pdf", description="Output format: 'pdf', 'json', or 'compact-pdf'"),
    include_empty: bool = Query(False, description="Include actors without names in output (JSON only)"),
    ocr_confidence: float = Query(0.3, description="OCR confidence threshold (0.1 to 1.0)")
):
    """
    Detect actors and use cases in an image and return results
    
    - **file**: Image file (PNG, JPG, etc.)
    - **debug**: Enable debug mode for detailed processing
    - **format**: Output format ('pdf', 'json', or 'compact-pdf')
    - **include_empty**: Include actors without names in JSON output
    - **ocr_confidence**: Minimum confidence threshold for OCR detection
    """
    # Validate file type
    allowed_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.webp'}
    file_extension = os.path.splitext(file.filename)[1].lower()
    
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed types: {', '.join(allowed_extensions)}"
        )
    
    # Validate OCR confidence
    if not 0.1 <= ocr_confidence <= 1.0:
        raise HTTPException(
            status_code=400,
            detail="OCR confidence must be between 0.1 and 1.0"
        )
    
    # Create temporary file
    temp_file_path = None
    processed_image_path = None
    
    try:
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension, dir=TEMP_DIR) as temp_file:
            shutil.copyfileobj(file.file, temp_file)
            temp_file_path = temp_file.name
        
        print(f"Processing file: {temp_file_path}")
        
        # Initialize detector and process image for ACTORS
        detector = DrawIOActorDetector(temp_file_path, debug=debug)
        actor_count, actor_positions, actors_list = detector.detect_actors()
        
        # Filter and renumber actors
        filtered_actors, stats = filter_and_renumber_actors(actors_list)
        
        # Extract actor names for blacklist (solo actores con nombre)
        actor_names = [name for _, name in filtered_actors if name and name.strip()]
        
        # Initialize UseCaseOCR with actor blacklist for USE CASES
        usecase_ocr = UseCaseOCR(
            temp_file_path, 
            actor_blacklist=actor_names, 
            gpu=False
        )
        
        # Run OCR to detect use cases (excluyendo textos de actores)
        usecase_results = usecase_ocr.run_ocr(confidence_threshold=ocr_confidence)
        usecase_list = usecase_ocr.get_use_cases()
        
        # If debug mode, save processed images
        if debug:
            processed_image_path = "actors_debug_output.png"
            usecase_ocr.save_results("usecases_results.json")
        
        # Prepare results
        detection_time = datetime.now().isoformat()
        
        # Return based on requested format
        if format.lower() == "json":
            # Prepare JSON response
            response_data = {
                "status": "success",
                "detection_time": detection_time,
                "statistics": {
                    "total_actors_detected": int(stats['total_detected']),
                    "actors_with_names": int(stats['with_names']),
                    "actors_without_names": int(stats['without_names']),
                    "use_cases_detected": int(len(usecase_list)),
                    "actors_in_final_report": int(len(filtered_actors))
                },
                "actors": [
                    {"actor_id": int(actor_id), "name": str(actor_name)}
                    for actor_id, actor_name in filtered_actors
                ],
                "use_cases": [
                    {"use_case_id": idx + 1, "description": str(use_case)}
                    for idx, use_case in enumerate(usecase_list)
                ],
                "positions": [
                    {"x": float(x), "y": float(y)}
                    for x, y in actor_positions
                ] if actor_positions else []
            }
            
            # Include empty actors if requested
            if include_empty:
                response_data["all_detected_actors"] = [
                    {"original_id": int(actor_id), "name": str(actor_name or "Sin nombre")}
                    for actor_id, actor_name in actors_list
                ]
                response_data["omitted_actors"] = [
                    int(actor_id) for actor_id, name in actors_list 
                    if not name or not name.strip()
                ]
            
            return JSONResponse(content=response_data)
        
        elif format.lower() == "pdf":
            # Generate PDF with actors and use cases
            pdf_buffer = create_actors_pdf(
                actors_list=actors_list,
                detection_date=detection_time,
                image_path=processed_image_path,
                use_cases_list=usecase_list
            )
            
            # Create filename for download
            original_name = os.path.splitext(file.filename)[0]
            pdf_filename = f"actores_casos_de_uso_{original_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            
            # Return PDF as streaming response
            return StreamingResponse(
                pdf_buffer,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename={pdf_filename}",
                    "Content-Type": "application/pdf"
                }
            )
        
        elif format.lower() == "compact-pdf":
            # Generate compact PDF with use cases
            pdf_buffer = create_compact_actors_pdf(
                actors_list=actors_list,
                use_cases_list=usecase_list
            )
            
            # Create filename for download
            pdf_filename = f"actores_casos_de_uso_compacto_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            
            # Return PDF as streaming response
            return StreamingResponse(
                pdf_buffer,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename={pdf_filename}",
                    "Content-Type": "application/pdf"
                }
            )
        
        else:
            raise HTTPException(
                status_code=400,
                detail="Invalid format. Choose 'pdf', 'json', or 'compact-pdf'"
            )
    
    except Exception as e:
        print(f"Error processing image: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing image: {str(e)}"
        )
    
    finally:
        # Clean up temporary files
        try:
            if temp_file_path and os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
        except Exception as e:
            print(f"Warning: Could not delete temp file: {e}")

@app.post("/detect-actors-simple/")
async def detect_actors_simple(
    file: UploadFile = File(..., description="Image file to process"),
    ocr_confidence: float = Query(0.3, description="OCR confidence threshold (0.1 to 1.0)")
):
    """
    Simple endpoint that returns only actors and use cases list in PDF format
    """
    # Validate file type
    allowed_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.webp'}
    file_extension = os.path.splitext(file.filename)[1].lower()
    
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed types: {', '.join(allowed_extensions)}"
        )
    
    # Validate OCR confidence
    if not 0.1 <= ocr_confidence <= 1.0:
        raise HTTPException(
            status_code=400,
            detail="OCR confidence must be between 0.1 and 1.0"
        )
    
    # Create temporary file
    temp_file_path = None
    
    try:
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension, dir=TEMP_DIR) as temp_file:
            shutil.copyfileobj(file.file, temp_file)
            temp_file_path = temp_file.name
        
        # Initialize detector and process image for ACTORS
        detector = DrawIOActorDetector(temp_file_path, debug=False)
        _, _, actors_list = detector.detect_actors()
        
        # Filter and renumber actors
        filtered_actors, stats = filter_and_renumber_actors(actors_list)
        
        # Extract actor names for blacklist (solo actores con nombre)
        actor_names = [name for _, name in filtered_actors if name and name.strip()]
        
        # Initialize UseCaseOCR with actor blacklist for USE CASES
        usecase_ocr = UseCaseOCR(
            temp_file_path, 
            actor_blacklist=actor_names, 
            gpu=False
        )
        
        # Run OCR to detect use cases (excluyendo textos de actores)
        usecase_results = usecase_ocr.run_ocr(confidence_threshold=ocr_confidence)
        usecase_list = usecase_ocr.get_use_cases()
        
        # Generate simple PDF with actors and use cases
        pdf_buffer = create_simple_actors_pdf(
            actors_list=actors_list,
            use_cases_list=usecase_list
        )
        
        # Create filename for download
        pdf_filename = f"actores_casos_de_uso_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        
        # Return PDF as streaming response
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={pdf_filename}",
                "Content-Type": "application/pdf"
            }
        )
    
    except Exception as e:
        print(f"Error processing image: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing image: {str(e)}"
        )
    
    finally:
        # Clean up temporary files
        try:
            if temp_file_path and os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
        except Exception as e:
            print(f"Warning: Could not delete temp file: {e}")

@app.get("/example-actors/")
async def get_example_actors():
    """
    Return example actors and use cases data without processing an image
    Useful for testing PDF generation
    """
    example_actors = [
        (1, "Usuario del Sistema"),
        (2, "Administrador"),
        (3, "Servicio de Pagos"),
        (4, "Base de Datos"),
        (5, "Sistema Externo")
    ]
    
    example_use_cases = [
        "Iniciar sesión en el sistema",
        "Registrar nuevo usuario",
        "Realizar pago en línea",
        "Consultar historial de transacciones",
        "Generar reporte mensual",
        "Configurar preferencias del sistema"
    ]
    
    pdf_buffer = create_actors_pdf(
        actors_list=example_actors,
        detection_date=datetime.now().isoformat(),
        use_cases_list=example_use_cases
    )
    
    pdf_filename = f"ejemplo_actores_casos_de_uso_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={pdf_filename}",
            "Content-Type": "application/pdf"
        }
    )

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )