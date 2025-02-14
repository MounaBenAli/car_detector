"""API endpoints."""
import hashlib
from flask import request
import io
from flask_restful import Resource
from werkzeug.utils import secure_filename
from detector import Pred
from .config import app
from werkzeug.datastructures import FileStorage
import requests
from .db import Prediction, Result
from pathlib import Path

class Predict(Resource):
    """Prediction endpoint."""

    def allowed_file(self):
        """Check if file extension is allowed."""
        return '.' in self.file.filename and self.file.filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

    def downloadfile(self):
        """Get picture from url."""
        try:
            response = requests.get(str(self.url))
        except Exception:
            return None
        self.filetype = response.headers.get('content-type')
        if self.filetype is None:
            ext = str(self.url).split('.')[-1]
            ext = ext.split('?')[0]
        # we get the filetype from http header if it exists
        else:
            ext = self.filetype.split('/')[-1]
        if response is not None:
            # turn the image into filestorage object to have the same file handling as the fil upload
            image_stream = io.BytesIO(response.content)
            file = FileStorage(stream=image_stream, filename=f"upload.{ext}")
            return file
        else:
            return None

    def post(self):
        """Post request."""
        self.url = request.form.get('url', type=str)

        if 'file' not in request.files and self.url is None:
            return {'Error':'No File or URL'}, 400

        if 'file' in request.files and self.url is not None:
            return {'Error':'Malformed Request'}, 400

        if 'file' in request.files:
            self.file = request.files['file']

        elif self.url is not None:
            self.file = self.downloadfile()
            if self.file is None:
                return {'Error':'Problem with downloading your file'}, 400

        if self.file and self.allowed_file():
            try:
                self.file.filename = secure_filename(str(self.file.filename))
                extension = self.file.filename.split(".")[1:]
                extension = '.'.join(extension)
                # getting the hash and saving the file
                self.file_hash = hashlib.md5(self.file.stream.read()).hexdigest()
                self.file_path = Path(self.file_hash+'.'+extension)
                self.file_path = app.config['UPLOAD_FOLDER'] / self.file_path
                self.file.stream.seek(0)
                if not self.file_path.is_file():
                    self.file.save(str(self.file_path))
            except Exception as e:
                return {'Error': 'Saving File Error',
                        'Description': str(e)}, 500
            try:
                # getting the prediciton results
                self.result = Pred(self.file_path)
                self.result = self.result.result
            except Exception as e:
                return {'Error':'AI Model Error',
                        'Description': str(e)}, 500
            try:
                result = Result(**self.result)
                prediction = Prediction(_id=str(self.file_hash), img_path='/'+str(self.file_path))
                prediction.result = result
                # saving the prediction results
                prediction.save()
            except Exception as e:
                return {'Error':'DB Error',
                        'Description': str(e)}, 500
            # to_mongo will ouput the dict representation of the object that was saved into db
            return prediction.to_mongo(), 201
        else:
            return {'Image types allowed':'png, jpg, jpeg, webp, jfif'}, 400


class GetPrediction(Resource):
    """Get Prediction endpoint."""

    def get(self):
        """Get request."""
        id = request.args.get('id', type=str)

        if not id:
            return {'Error': 'No id'}, 400

        try:
            obj = Prediction.objects(_id=id).first()
        except Exception as e:
            return {'Error': 'DB Error', 'Description': str(e)}, 500

        if not obj:
            return {'Error': 'Not found'}, 404

        return obj.to_mongo(), 200
