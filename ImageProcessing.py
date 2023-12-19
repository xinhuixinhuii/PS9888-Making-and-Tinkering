import cv2
import numpy as np
import time
import os

class Pen:
    def __init__(self, pen_properties_str, pen_offset):
        pen_properties = pen_properties_str.rstrip().split(" | ")
        self.hex = pen_properties[0]
        self.bgr = np.array([int(self.hex[5:7], 16), int(self.hex[3:5], 16), int(self.hex[1:3], 16)])
        self.rel_home = np.array([float(i) for i in pen_properties[1].split()])
        self.abs_home = (self.rel_home + pen_offset)
        self.colour = pen_properties[2]
        self.map = []
        self.rel_map = []
        self.abs_map = []

    def optimise(self):
        if len(self.map) != 0:
            og_map = self.map
            new_map = [og_map[0]]
            og_map.pop(0)
            while len(og_map) != 0:
                shortest_distance = np.linalg.norm(new_map[-1] - og_map[0])
                index = 0
                for i in range(1, len(og_map)):
                    distance = np.linalg.norm(new_map[-1] - og_map[i])
                    if distance == 1:
                        index = i
                        break
                    if distance < shortest_distance:
                        shortest_distance = distance
                        index = i
                new_map.append(og_map[index])
                og_map.pop(index)
            self.map = new_map

    def movement(self, canvas_offset, size, resolution):
        pixel_size = size[0] / resolution[0]
        self.rel_map = [np.array([i[1], i[0], 0]) * pixel_size for i in self.map]
        self.abs_map = [i + canvas_offset for i in self.rel_map]

    def instruction(self, instruction_data, ceiling, lift):
        instruction_data.write(
            "G01 X{:0>6.2f} Y{:0>6.2f} Z{:0>6.2f}\n".format(self.abs_home[0], self.abs_home[1], ceiling))
        instruction_data.write("G01                 Z{:0>6.2f}\n".format(self.abs_home[2]))
        instruction_data.write("G01                 Z{:0>6.2f}\n".format(ceiling))
        for location in self.abs_map:
            instruction_data.write("G01 X{:0>6.2f} Y{:0>6.2f}        \n".format(location[0], location[1]))
            instruction_data.write("G01                 Z{:0>6.2f}\n".format(location[2]))
            instruction_data.write("G01                 Z{:0>6.2f}\n".format(location[2] + lift))
        instruction_data.write("G01                 Z{:0>6.2f}\n".format(ceiling))


def resize_filter(img, resolution, background, mode="fit", interpolation=cv2.INTER_CUBIC):
    height, width, channels = img.shape
    if mode == "stretch":
        new_img = cv2.resize(img, resolution, interpolation)
    if mode == "fill":
        if width / height >= resolution[1] / resolution[0]:
            new_width = int(resolution[0] / height * width)
            new_img = cv2.resize(img, (new_width, resolution[0]), interpolation)[:, (new_width - resolution[1]) // 2:
                                                                                    (new_width + resolution[1]) // 2]
        else:
            new_height = int(resolution[1] / width * height)
            new_img = cv2.resize(img, (resolution[1], new_height), interpolation)[
                      (new_height - resolution[0]) // 2:(new_height + resolution[0]) // 2, :]
    if mode == "fit":
        if width / height >= resolution[1] / resolution[0]:
            new_height = int(resolution[1] / width * height)
            new_img = cv2.resize(img, (resolution[1], new_height), interpolation)
            new_img = cv2.copyMakeBorder(new_img, (resolution[0] - new_height) // 2,
                                         resolution[0] - new_height - (resolution[0] - new_height) // 2, 0, 0,
                                         cv2.BORDER_CONSTANT, value=background.tolist())
        else:
            new_width = int(resolution[0] / height * width)
            new_img = cv2.resize(img, (new_width, resolution[0]), interpolation)
            new_img = cv2.copyMakeBorder(new_img, 0, 0, (resolution[1] - new_width) // 2,
                                         resolution[1] - new_width - (resolution[1] - new_width) // 2,
                                         cv2.BORDER_CONSTANT, value=background.tolist())
    return new_img


def colour_approximation_filter(img, pens, background, dithering=True):
    def approximate_colour(og_pixel_bgr, pens, background):
        min_error = np.linalg.norm(background - og_pixel_bgr)
        pixel_bgr = background
        for pen in pens:
            error = np.linalg.norm(pen.bgr - og_pixel_bgr)
            if error < min_error:
                min_error = error
                pixel_bgr = pen.bgr
        return pixel_bgr

    def dither(new_img, y, x, og_pixel_bgr, pixel_bgr, coefficient_mapping):
        def clip(value):
            if value < 0:
                value = 0
            if value > 255:
                value = 255
            return value

        for c in range(3):
            quant_error = int(og_pixel_bgr[c]) - int(pixel_bgr[c])
            for pixel_offset, coefficient in coefficient_mapping.items():
                new_img[y + pixel_offset[0], x + pixel_offset[1], c] = clip(
                    int(new_img[y + pixel_offset[0], x + pixel_offset[1], c] + quant_error * coefficient))

    new_img = cv2.copyMakeBorder(img, 0, 1, 1, 1, cv2.BORDER_CONSTANT, value=background.tolist())
    height, width, channels = new_img.shape
    coefficient_mapping = {(0, 1): 7 / 16, (1, -1): 3 / 16, (1, 0): 5 / 16, (1, 1): 1 / 16}
    for y in range(0, height - 1):
        for x in range(1, width - 1):
            og_pixel_bgr = new_img[y, x]
            pixel_bgr = approximate_colour(og_pixel_bgr, pens, background)
            if dithering:
                dither(new_img, y, x, og_pixel_bgr, pixel_bgr, coefficient_mapping)
            new_img[y, x] = pixel_bgr
    new_img = new_img[0:height - 1, 1:width - 1]
    return new_img


def record(img, pens):
    height, width, channels = img.shape
    for y in range(height):
        for x in range(width):
            for pen in pens:
                if np.array_equal(pen.bgr, img[y, x]):
                    pen.map.append(np.array([y, x]))


# source files
pen_data_file = "ImageProcessing/Pen Data Monochrome.txt"
image_file = "ImageProcessing/Mona_Lisa,_by_Leonardo_da_Vinci,_from_C2RMF_retouched.jpg"
instruction_data_file = "ImageProcessing/Instruction.gcode"

# adjustable perimeters
background = np.array([255, 255, 255])  # background colour (b, g, r)
pen_offset = np.array([110, 0, 60])  # initial pen grabbing position  (x, y, z)
resolution = np.array([50, 50])  # resolution of the drawn image (y, x)
display_size = np.array([600, 600])  # preview window size (y, x)
mode = "fill"  # resizing mode (stretch, fill, and fit)
interpolation = cv2.INTER_CUBIC  # resizing mode  (NEAREST, LINEAR, AREA, CUBIC, LANCZOS4)
dithering = True  # dithering switch
preview = True  # preview switch
time_report = True  # print processing time

canvas_offset = np.array([0, 50, 10])  # initial drawing position  (x, y, z)
size = np.array([100, 100])  # canvas size (in mm) (y, x)
lift = 1  # lifting height between drawing each dot
ceiling = 200  # lifting height between changing pens

COUNT = 1

# ______________________________________________________________________________________________________________________
# START OF THE PROCESS
def Image2Gcode(filename):
    image_file = filename
    instruction_data_file = filename +".gcode"
    print(type(image_file))
    print("Please wait...")

    # read the pen data
    pens = []
    pen_data = open(pen_data_file, "r")
    for pen_properties_str in pen_data:
        pens.append(Pen(pen_properties_str, pen_offset))  # generate instances in "Pen" class
    pen_data.close()

    # read the image data
    img = cv2.imread(image_file)
    print(type(img))

    # process the image
    img = resize_filter(img, resolution, background, mode, interpolation)  # resizing the image
    img = colour_approximation_filter(img, pens, background, dithering)  # limit the colours used in the image

    # record the pixels in the processed image to generate G-code
    record(img, pens)

    # rearrange the coordinates for a more optimal path and generate the map with absolute coordinates
    for pen in pens:
        pen.optimise()
        pen.movement(canvas_offset, size, resolution)

    # write the G-code
    instruction_data = open(instruction_data_file, "w")
    
    #REMOVED G28\n 25/8/22
    instruction_data.write("G21\n")  # metric (mm)
    for pen in pens:
        if len(pen.abs_map) != 0:
            pen.instruction(instruction_data, ceiling, lift)
    instruction_data.close()

    '''
    # display the preview
    if preview:
        cv2.namedWindow(image_file + " (preview)", cv2.WINDOW_NORMAL)
        cv2.resizeWindow(image_file + " (preview)", display_size[0], display_size[1])
        cv2.imshow(image_file + " (preview)", img)
    '''

    # print the processing time
    if time_report:
        print("Time elapsed: {:d} min {:.3f} s".format(int(time.process_time() / 60),
                                                    time.process_time() - time.process_time() // 60 * 60))

    # hold the preview
    if preview:
        cv2.waitKey()
        

