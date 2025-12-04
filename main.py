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

# Import your detector and PDF builder
from actor_detector import DrawIOActorDetector  # Renamed from your original code
from pdf_builder import create_actors_pdf, create_compact_actors_pdf, create_simple_actors_pdf, filter_and_renumber_actors

app = FastAPI(
    title="Actor Detection API",
    description="API para detección de actores en diagramas y generación de reportes PDF",
    version="1.0.0"
)

# Temporary directory for uploaded files
TEMP_DIR = "tmp"
os.makedirs(TEMP_DIR, exist_ok=True)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] , 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"], 
)

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Actor Detection API",
        "endpoints": {
            "detect_actors": "POST /detect-actors/ - Upload image and detect actors",
            "health": "GET /health/ - API health check"
        },
        "version": "1.0.0"
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
    include_empty: bool = Query(False, description="Include actors without names in output (JSON only)")
):
    """
    Detect actors in an image and return results in specified format
    
    - **file**: Image file (PNG, JPG, etc.)
    - **debug**: Enable debug mode for detailed processing
    - **format**: Output format ('pdf', 'json', or 'compact-pdf')
    - **include_empty**: Include actors without names in JSON output
    """
    # Validate file type
    allowed_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.webp'}
    file_extension = os.path.splitext(file.filename)[1].lower()
    
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed types: {', '.join(allowed_extensions)}"
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
        
        # Initialize detector and process image
        detector = DrawIOActorDetector(temp_file_path, debug=debug)
        actor_count, actor_positions, actors_list = detector.detect_actors()
        
        # Filter and renumber actors
        filtered_actors, stats = filter_and_renumber_actors(actors_list)
        
        # Prepare results
        detection_time = datetime.now().isoformat()
        
        # If debug mode, save processed image
        if debug:
            processed_image_path = "actors_debug_output.png"
        
        # Return based on requested format
        if format.lower() == "json":
            # Preparar respuesta JSON CONVERTIENDO tipos numpy a python nativo
            response_data = {
                "status": "success",
                "detection_time": detection_time,
                "statistics": {
                    "total_detected": int(stats['total_detected']),  # Convertir a int
                    "with_names": int(stats['with_names']),  # Convertir a int
                    "without_names": int(stats['without_names']),  # Convertir a int
                    "in_final_report": int(len(filtered_actors))  # Convertir a int
                },
                "actors": [
                    {"actor_id": int(actor_id), "name": str(actor_name)}  # Convertir tipos
                    for actor_id, actor_name in filtered_actors
                ],
                "positions": [
                    {"x": float(x), "y": float(y)}  # Convertir a float
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
            # Generate PDF
            pdf_buffer = create_actors_pdf(
                actors_list=actors_list,
                detection_date=detection_time,
                image_path=processed_image_path
            )
            
            # Create filename for download
            original_name = os.path.splitext(file.filename)[0]
            pdf_filename = f"actores_{original_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            
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
            # Generate compact PDF
            pdf_buffer = create_compact_actors_pdf(actors_list)
            
            # Create filename for download
            pdf_filename = f"actores_compacto_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            
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
    file: UploadFile = File(..., description="Image file to process")
):
    """
    Simple endpoint that returns only the actors list in PDF format
    """
    # Validate file type
    allowed_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.webp'}
    file_extension = os.path.splitext(file.filename)[1].lower()
    
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed types: {', '.join(allowed_extensions)}"
        )
    
    # Create temporary file
    temp_file_path = None
    
    try:
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension, dir=TEMP_DIR) as temp_file:
            shutil.copyfileobj(file.file, temp_file)
            temp_file_path = temp_file.name
        
        # Initialize detector and process image
        detector = DrawIOActorDetector(temp_file_path, debug=False)
        _, _, actors_list = detector.detect_actors()
        
        # Generate simple PDF
        pdf_buffer = create_simple_actors_pdf(actors_list)
        
        # Create filename for download
        pdf_filename = f"actores_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        
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
    Return example actors data without processing an image
    Useful for testing PDF generation
    """
    example_actors = [
        (1, "Usuario del Sistema"),
        (2, "Administrador"),
        (3, "Servicio de Pagos"),
        (4, "Base de Datos"),
        (5, "Sistema Externo")
    ]
    
    pdf_buffer = create_actors_pdf(
        actors_list=example_actors,
        detection_date=datetime.now().isoformat()
    )
    
    pdf_filename = f"ejemplo_actores_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    
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
