import base64
import copy
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import unittest
import zlib
from unittest.mock import patch
from Sources.calendar_domain import ConflictError, ValidationError
from Sources.calendar_domain.place_images import MAX_IMAGE_BYTES, display_jpeg, prepare_image
from test_places import PlacesTest


def png(width=24,height=12,color=(20,130,210)):
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+bytes(color)*width)*height))+chunk(b'IEND',b'')


class PlaceImagesTest(unittest.TestCase):
    setUp=PlacesTest.setUp

    def request(self,action='remove',raw=None,rid='image-1',identity=4):
        result=dict(request_id=rid,id=identity,expected_revision=self.cal.get_place(identity)['revision'],action=action)
        if raw is not None:result['image_base64']=base64.b64encode(raw).decode()
        return result

    def test_simple_external_image_and_clear_cli_keep_records(self):
        before=self.cal.list_castles()
        # No introduction, author/license checklist, migration or external image fetch is required.
        old=self.cal.get_place(4)
        self.cal.apply_place_request(dict(request_id='external',id=4,expected_revision=old['revision'],values={'image':{'url':'https://example.com/allowed.jpg','source_url':'https://example.com/'}}))
        request=self.request()
        result=self.cal.apply_place_image_request(request)
        self.assertIsNone(result['receipt']['item']['image'])
        self.assertEqual(self.cal.apply_place_image_request(request)['receipt'],result['receipt'])
        self.assertEqual(self.cal.lookup_place_request(request['request_id'])['receipt'],result['receipt'])
        with self.assertRaises(ConflictError):self.cal.apply_place_image_request(dict(request,action='set',image_base64=base64.b64encode(png()).decode()))
        with self.assertRaises(ConflictError):self.cal.apply_place_image_request(dict(request,request_id='stale'))
        self.assertEqual(self.cal.list_castles(),before)
        req=self.request(rid='cli-remove')
        command=[sys.executable,'-B','scripts/cal_places.py','--database',str(self.db),'--local-root',str(self.root)]
        p=subprocess.run(command+['image'],input=json.dumps(req),capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        r=json.loads(p.stdout)['receipt'];self.assertEqual(r['image_action'],'remove')
        p=subprocess.run(command+['lookup','--request-id','cli-remove'],capture_output=True,text=True)
        self.assertEqual(json.loads(p.stdout)['receipt'],r)
        self.assertEqual(self.cal.list_castles(),before)

    @unittest.skipUnless(Path('/usr/bin/sips').exists(),'native Mac image conversion')
    def test_upload_replace_clear_replay_conflict_and_preserve_seed(self):
        before=self.cal.list_castles();seed=self.samples[5]
        self.cal.apply_place_request(dict(request_id='sample',id=1001,expected_revision=None,values=seed['values']))
        original=self.cal.get_place(1001)
        raw=png(2000,1000)
        request=self.request('set',raw,identity=1001)
        result=self.cal.apply_place_image_request(request);receipt=result['receipt'];image=receipt['item']['image']
        self.assertEqual((image['width'],image['height']),(1600,800))
        self.assertEqual(receipt['source_sha256'],hashlib.sha256(raw).hexdigest())
        key=image['url'].rsplit('/',1)[1];data=self.cal.read_place_image(key)
        self.assertTrue(data.startswith(b'\xff\xd8'))
        self.assertEqual(key,hashlib.sha256(data).hexdigest()+'.jpg')
        with patch('Sources.calendar_domain.place_images.prepare_image',side_effect=AssertionError('must replay before conversion')):
            self.assertEqual(self.cal.apply_place_image_request(request)['receipt'],receipt)
        self.assertEqual(self.cal.lookup_place_request(request['request_id'])['receipt'],receipt)
        replacement=self.request('set',png(color=(210,30,20)),rid='replace',identity=1001)
        result=self.cal.apply_place_image_request(replacement)
        self.assertNotEqual(result['receipt']['item']['image']['url'],image['url'])
        remove=self.request(rid='remove',identity=1001);self.cal.apply_place_image_request(remove)
        current=self.cal.get_place(1001);self.assertIsNone(current['image'])
        for key in original:
            if key not in ('image','revision'):self.assertEqual(current[key],original[key])
        self.assertEqual(self.cal.list_castles(),before)
        with self.assertRaises(ConflictError):self.cal.apply_place_image_request(dict(replacement,request_id='stale'))
        # Also works for a castle that has neither an introduction nor sources.
        self.cal.apply_place_image_request(self.request('set',png(),rid='unintroduced'))
        self.assertEqual(self.cal.list_castles(),before)

    def test_reject_input_and_storage_failure_without_change(self):
        before=self.cal.get_place(4)
        for change in ({'image_base64':'!!!'},{'image_base64':'A'*(((MAX_IMAGE_BYTES+2)//3)*4+4)},{'action':'delete-everything'},{'expected_revision':None}):
            req=self.request('set',png());req.update(change)
            with self.assertRaises(ValidationError):self.cal.apply_place_image_request(req)
            self.assertEqual(self.cal.get_place(4),before)
        with patch('Sources.calendar_domain.place_images.prepare_image',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.cal.apply_place_image_request(self.request('set',png()))
        self.assertEqual(self.cal.get_place(4),before)
        self.assertEqual(self.cal.lookup_place_request('image-1')['status'],'not_found')
        with self.assertRaises(ValidationError):self.cal.read_place_image('../../db/calendar.sqlite3')

    @unittest.skipUnless(Path('/usr/bin/sips').exists(),'native Mac image conversion')
    def test_native_formats_invalid_file_and_orientation_metadata(self):
        data,w,h=prepare_image(png(),self.root/'images')
        self.assertEqual((w,h),(24,12))  # Small images are not enlarged.
        with self.assertRaises(ValidationError):prepare_image(b'<svg onload="bad"></svg>',self.root/'images')
        # A minimal orientation record survives; GPS/comments/XMP do not.
        tiff=b'Exif\0\0II*\0\x08\0\0\0\x01\0'+struct.pack('<HHI',274,3,1)+b'\x06\0\0\0'+b'\0'*4
        jpeg=b'\xff\xd8'+b'\xff\xe1'+struct.pack('>H',len(tiff)+2)+tiff+b'\xff\xfe\0\x08SECRET'+data[2:]
        stripped,direction=display_jpeg(jpeg)
        self.assertEqual(direction,6);self.assertNotIn(b'SECRET',stripped)
        self.assertEqual(display_jpeg(stripped)[1],6)


if __name__=='__main__':unittest.main()
