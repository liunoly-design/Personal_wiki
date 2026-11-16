"""Identify downloaded raster formats so extensionless CDN images reach OCR."""
def image_extension(data):
    if data.startswith(b'\xff\xd8\xff'):return '.jpg'
    if data.startswith(b'\x89PNG\r\n\x1a\n'):return '.png'
    if data.startswith((b'GIF87a',b'GIF89a')):return '.gif'
    if data.startswith(b'RIFF') and data[8:12]==b'WEBP':return '.webp'
    raise ValueError('Image response is not a supported image; retained for diagnosis')
