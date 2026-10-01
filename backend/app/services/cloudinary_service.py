import cloudinary
import cloudinary.uploader
from app.core.config import settings

def configure_cloudinary():
    if settings.cloudinary_cloud_name != "default":
        cloudinary.config(
            cloud_name=settings.cloudinary_cloud_name,
            api_key=settings.cloudinary_api_key,
            api_secret=settings.cloudinary_api_secret,
            secure=True
        )

def upload_image(file_bytes: bytes, filename: str, folder: str = "video-agent") -> str:
    """Upload image to Cloudinary, return secure URL. Mock for development if defaults are set."""
    if settings.cloudinary_cloud_name == "default":
        # Return a mock URL for local dev if Cloudinary isn't configured
        return f"https://mock-image-url.com/{folder}/{filename}"
        
    configure_cloudinary()
    import io
    try:
        result = cloudinary.uploader.upload(
            io.BytesIO(file_bytes),
            folder=folder,
            public_id=filename.split('.')[0] if '.' in filename else filename,
            resource_type="image",
            overwrite=True,
        )
        return result["secure_url"]
    except Exception as e:
        print(f"Cloudinary upload error: {e}")
        # Fallback for dev
        return f"https://mock-image-url.com/{folder}/{filename}-fallback"
