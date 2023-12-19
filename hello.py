from fnmatch import fnmatch
import imghdr
import os
from flask import Flask, render_template, request, redirect, url_for, abort, \
    send_from_directory, send_file
from werkzeug.utils import secure_filename
import ImageProcessing.ImageProcessing as ImageProcessing
from utils import *
import sys
import time

app = Flask(__name__)
app.config['UPLOAD_EXTENSIONS'] = ['.jpg', '.png']
app.config['UPLOAD_PATH'] = 'uploads'

COUNT = 1

def validate_image(stream):
    header = stream.read(512)
    stream.seek(0)
    format = imghdr.what(None, header)
    if not format:
        return None
    return '.' + (format if format != 'jpeg' else 'jpg')

@app.route('/')
def index():
    files = os.listdir(app.config['UPLOAD_PATH'])
    return render_template('index.html', files=files)

@app.route('/', methods=['POST', 'GET'])
def upload_files():
    uploaded_file = request.files['file']
    filename = secure_filename(uploaded_file.filename)

    if filename != '':
        file_ext = os.path.splitext(filename)[1]
        if file_ext not in app.config['UPLOAD_EXTENSIONS'] or \
                file_ext != validate_image(uploaded_file.stream):
            return "Invalid image", 400
        uploaded_file.save(os.path.join(app.config['UPLOAD_PATH'], filename))
        print(filename, "is uploaded at /uploads/"+filename)
        
        '''
        print('Outlining.....')
        img = convertLineArt('uploads/'+filename)
        print('Line Art Done.....')
        convertBitMap(img)
        print('Bit Map Done.....')
        convertGcode()
        print('Converting to GCODE.....')
        '''
        
        print('Dotting.....')
        ImageProcessing.Image2Gcode('uploads/'+filename)

        global COUNT
        oldname = 'uploads/' + filename +".gcode"
        newname = "uploads/gcode" + str(COUNT) +".gcode"
        os.rename(oldname, newname)
        path='uploads/gcode'+str(COUNT)+'.gcode'
        COUNT += 1

        return send_file(path, as_attachment=True)

@app.route('/calibrate', methods=['POST', 'GET'])
def calibration():
    if request.method == 'POST':
        form_data = request.form
        print(form_data)
        x = form_data['X Offset']
        y = form_data['Y Offset']
        z = form_data['Z Offset']
        new_line = 'G28\nG01 X'+x+' Y'+y+' Z'+z+'\nG92 X0 Y0 Z0\n'
        print(new_line)

        
        directory = 'C:/PS9888/Automated-Rubik-Cube-Painting-main - Copy/uploads'
        for file in os.listdir(directory):
            f=os.path.join(directory, file)
            if os.path.isfile(f):
                if fnmatch(file, '*.gcode'):
                    with open(f, 'r+') as gcode:
                        content = gcode.read()
                        gcode.seek(0)
                        gcode.write(new_line + content)
        
        return f"Success! Please check /uploads for the Gcode Files."

@app.route('/uploads/<filename>')
def upload(filename):
    return send_from_directory(app.config['UPLOAD_PATH'], filename)
