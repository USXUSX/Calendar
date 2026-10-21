"""CAL-owned single representative image. Native macOS decoding; no Photos-library writes."""
import base64
import binascii
import hashlib
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
from datetime import datetime, timezone
from .errors import ConflictError, NotFoundError, ValidationError
from .schedule_chat import encoded, request_id

MAX_IMAGE_BYTES = 12 * 1024 * 1024
LOCAL_IMAGE = re.compile(r'^/api/calendar/places/images/([0-9a-f]{64})\.jpg$')


def validate_image(image):
    if image is None: return
    if not isinstance(image, dict) or not isinstance(image.get('url'), str):
        raise ValidationError('image_url_required')
    if image.get('source') == 'upload':
        if not LOCAL_IMAGE.fullmatch(image['url']): raise ValidationError('invalid_local_image')
        return
    from .places import url
    url(image['url'])
    if image.get('display', 'image') not in ('image', 'embed'): raise ValidationError('invalid_image_display')
    if 'reusable' in image and type(image['reusable']) is not bool: raise ValidationError('invalid_image_permission')
    for key in ('source_url', 'license_url'):
        if image.get(key): url(image[key])
    # Source-specific attribution is retained when supplied, but is not mandatory for every image.
    for key in ('credit', 'license', 'conditions', 'captured_at', 'changes', 'checked_at'):
        if key in image and not isinstance(image[key], str): raise ValidationError('invalid_image_metadata')


def orientation(exif):
    """Read just EXIF orientation; all other EXIF/GPS/XMP is omitted from the stored display image."""
    try:
        if not exif.startswith(b'Exif\0\0'): return 1
        tiff=exif[6:]; endian='<' if tiff[:2]==b'II' else '>'
        offset=struct.unpack_from(endian+'I',tiff,4)[0]
        count=struct.unpack_from(endian+'H',tiff,offset)[0]
        for i in range(count):
            tag,kind,n,value=struct.unpack_from(endian+'HHI4s',tiff,offset+2+i*12)
            if tag==274 and kind==3 and n==1:
                result=struct.unpack(endian+'H',value[:2])[0]
                return result if 1<=result<=8 else 1
    except (struct.error, IndexError): pass
    return 1


def display_jpeg(data):
    if not data.startswith(b'\xff\xd8'): raise ValidationError('invalid_image_conversion')
    position=2; chunks=[]; direction=1
    while position<len(data):
        marker=data[position:position+2]
        if marker in (b'\xff\xda', b'\xff\xd9'):
            chunks.append(data[position:]);break
        if len(marker)!=2 or marker[0]!=255: raise ValidationError('invalid_image_conversion')
        size=int.from_bytes(data[position+2:position+4],'big')
        if size<2 or position+2+size>len(data): raise ValidationError('invalid_image_conversion')
        chunk=data[position:position+2+size]
        if marker==b'\xff\xe1': direction=orientation(chunk[4:]) if chunk[4:].startswith(b'Exif\0\0') else direction
        if marker not in (b'\xff\xe1',b'\xff\xed',b'\xff\xfe'): chunks.append(chunk)
        position+=2+size
    exif=b''
    if direction!=1:
        payload=b'Exif\0\0II*\x00\x08\x00\x00\x00\x01\x00'+struct.pack('<HHI',274,3,1)+struct.pack('<H',direction)+b'\0\0'+b'\0'*4
        exif=b'\xff\xe1'+struct.pack('>H',len(payload)+2)+payload
    return b'\xff\xd8'+exif+b''.join(chunks),direction


def prepare_image(raw, directory):
    """Decode accepted raster formats and produce a <=1600px JPEG, retaining only orientation metadata."""
    directory.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.image-',dir=directory) as tmp:
        source=Path(tmp)/'input';target=Path(tmp)/'display.jpg';source.write_bytes(raw)
        try:
            probe=subprocess.run(['/usr/bin/sips','-g','format','-g','pixelWidth','-g','pixelHeight',str(source)],capture_output=True,text=True,timeout=20,check=True)
            props=dict(re.findall(r'^\s+(format|pixelWidth|pixelHeight):\s*(\S+)',probe.stdout,re.M))
            if props.get('format') not in ('jpeg','png','heic','heif','webp'): raise ValueError
            width=int(props['pixelWidth']);height=int(props['pixelHeight'])
            if width<1 or height<1 or width*height>50_000_000: raise ValueError
            args=['/usr/bin/sips','-s','format','jpeg','-s','formatOptions','80']
            if max(width,height)>1600: args+=['-Z','1600']
            subprocess.run(args+[str(source),'--out',str(target)],capture_output=True,timeout=30,check=True)
            data,direction=display_jpeg(target.read_bytes())
        except (ValueError, KeyError, subprocess.CalledProcessError):
            raise ValidationError('invalid_image_use_jpeg_png_heic_webp') from None
        except (FileNotFoundError, subprocess.TimeoutExpired):
            raise ValidationError('image_conversion_unavailable') from None
    scale=min(1,1600/max(width,height));width=max(1,round(width*scale));height=max(1,round(height*scale))
    if direction in (5,6,7,8):width,height=height,width
    return data,width,height


class PlaceImagesMixin:
    def apply_place_image_request(self, request):
        from .places import place_id
        if not isinstance(request, dict) or set(request)-{'request_id','id','expected_revision','action','image_base64'} or not {'request_id','id','expected_revision','action'}<=set(request):
            raise ValidationError('invalid_image_request')
        rid=request_id(request['request_id']);identity=place_id(request['id']);action=request['action']
        if not isinstance(request['expected_revision'],str) or not request['expected_revision']: raise ValidationError('expected_revision_required')
        raw=None;source_sha=None
        if action=='set':
            value=request.get('image_base64')
            if not isinstance(value,str) or not value or len(value)>((MAX_IMAGE_BYTES+2)//3)*4: raise ValidationError('image_too_large_or_missing')
            try:raw=base64.b64decode(value,validate=True)
            except (binascii.Error,ValueError):raise ValidationError('invalid_image_base64') from None
            if not raw or len(raw)>MAX_IMAGE_BYTES:raise ValidationError('image_too_large_or_missing')
            source_sha=hashlib.sha256(raw).hexdigest()
        elif action!='remove' or request.get('image_base64') is not None:
            raise ValidationError('invalid_image_action')
        digest=hashlib.sha256(encoded(dict(request_id=rid,id=identity,expected_revision=request['expected_revision'],action=action,source_sha256=source_sha)).encode()).hexdigest()
        with self._read() as c:
            prior=c.execute('SELECT * FROM place_receipts WHERE request_id=?',(rid,)).fetchone()
            if prior:
                if prior['payload_hash']!=digest:raise ConflictError('request_id_payload_conflict')
                import json
                return dict(status='committed',resolution='replayed',receipt=json.loads(prior['receipt_json']))
        current=self.get_place(identity)
        if current['revision']!=request['expected_revision']:raise ConflictError('revision_conflict')
        image=None
        if raw is not None:
            directory=self.trip_root/'place-images'
            data,width,height=prepare_image(raw,directory)
            key=hashlib.sha256(data).hexdigest();target=directory/(key+'.jpg')
            if not target.exists():
                fd,temp=tempfile.mkstemp(prefix='.display-',dir=directory)
                try:
                    with os.fdopen(fd,'wb') as handle:handle.write(data)
                    os.replace(temp,target)
                finally:
                    Path(temp).unlink(missing_ok=True)
            image=dict(source='upload',url='/api/calendar/places/images/'+key+'.jpg',width=width,height=height,
                       uploaded_at=datetime.now(timezone.utc).isoformat(),source_sha256=source_sha)
        command=dict(request_id=rid,id=identity,expected_revision=request['expected_revision'],values={'image':image})
        return self._commit_place_request(command,digest,dict(image_action=action,source_sha256=source_sha))

    def read_place_image(self, key):
        if not isinstance(key,str) or not re.fullmatch(r'[0-9a-f]{64}\.jpg',key):raise ValidationError('invalid_image_key')
        try:return (self.trip_root/'place-images'/key).read_bytes()
        except FileNotFoundError:raise NotFoundError('place_image_not_found') from None
