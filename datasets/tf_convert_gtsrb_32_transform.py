# Copyright 2016 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Converts GTSRB data to TFRecords of TF-Example protos.

This module downloads the MNIST data, uncompresses it, reads the files
that make up the MNIST data and creates two TFRecord datasets: one for train
and one for test. Each TFRecord dataset is comprised of a set of TF-Example
protocol buffers, each of which contain a single image and label.
"""

import os
import sys
import pickle

import numpy as np
import tensorflow as tf
import cv2

from datasets import dataset_utils
from datasets import gtsrb_32_transform

_TRAIN_FILENAME = 'train.p'
_TEST_FILENAME = 'test.p'

_IMAGE_SIZE = 32
_NUM_CHANNELS = 3
_NUM_CLASSES = 43

# The names of the classes.
_CLASS_NAMES = [
    str(i) for i in range(_NUM_CLASSES)
]


def _random_transform(img, max_angle, scale_range):
    """Apply some random transform (rotation + scaling) to an image.

    Sample uniformly the transformation parameters.
    Used for data augmentation when converting to TFRecords.
    """
    rows, cols, chs = img.shape

    # Rotation and scaling. Note: reverse axis on OpenCV
    angle = np.random.uniform(low=-max_angle, high=max_angle)
    rot_matrix = cv2.getRotationMatrix2D((cols / 2, rows / 2), angle, 1.)
    img = cv2.warpAffine(img, rot_matrix, (cols, rows))

    # Scaling matrix: keep image centered after scaled.
    scale_x = np.random.uniform(low=scale_range[0], high=scale_range[1])
    scale_y = np.random.uniform(low=scale_range[0], high=scale_range[1])
    scale_matrix = np.array([[scale_x, 0., (1. - scale_x) * cols / 2.],
                             [0., scale_y, (1. - scale_y) * rows / 2.]],
                            dtype=np.float32)
    img = cv2.warpAffine(img, scale_matrix, (cols, rows))
    return img


def _extract_images_labels(filename):
    """Extract the images and labels into a numpy array.
    Args:
      filename: The path to the images file.
    Returns:
      A numpy array of shape [number_of_images, height, width, channels].
    """
    print('Extracting images and labels from: ', filename)
    with open(filename, mode='rb') as f:
        data = pickle.load(f)
        images = data['features']
        labels = data['labels']
    return images.astype(np.uint8), labels.astype(np.int64)


def _add_to_tfrecord(data_filename, tfrecord_writer, augment=False):
    """Loads data from the Pickle files and writes files to a TFRecord.

    Args:
      data_filename: The filename of the images and labels.
      tfrecord_writer: The TFRecord writer to use for writing.
    """
    max_angle = 10.
    scale_range = [0.8, 1.2]

    images, labels = _extract_images_labels(data_filename)
    num_images = images.shape[0]

    shape = (_IMAGE_SIZE, _IMAGE_SIZE, _NUM_CHANNELS)
    with tf.Graph().as_default():
        image = tf.placeholder(dtype=tf.uint8, shape=shape)
        encoded_png = tf.image.encode_png(image)

        with tf.Session('') as sess:
            if augment:
                # Data augmentation...
                for j in range(_NUM_CLASSES):
                    sys.stdout.write('\r>> Converting and augmenting image class %d/%d' % (j + 1, _NUM_CLASSES))
                    sys.stdout.flush()

                    # Images indexes.
                    idxes = np.argwhere(labels == j)

                    for i in range(gtsrb_32_transform.NUM_ITEM_PER_CLASS):
                        idx = idxes[i % len(idxes)][0]
                        img = _random_transform(images[idx], max_angle, scale_range)
                        label = labels[idx]

                        png_string = sess.run(encoded_png, feed_dict={image: img})
                        example = dataset_utils.image_to_tfexample(
                            png_string, b'png', _IMAGE_SIZE, _IMAGE_SIZE, int(label))
                        tfrecord_writer.write(example.SerializeToString())

            else:
                # Just copy!
                for j in range(num_images):
                    sys.stdout.write('\r>> Converting image %d/%d' % (j + 1, num_images))
                    sys.stdout.flush()

                    png_string = sess.run(encoded_png, feed_dict={image: images[j]})
                    example = dataset_utils.image_to_tfexample(
                        png_string, b'png', _IMAGE_SIZE, _IMAGE_SIZE, int(labels[j]))
                    tfrecord_writer.write(example.SerializeToString())


def _get_output_filename(dataset_dir, split_name):
    filename = gtsrb_32_transform.FILE_PATTERN % split_name
    return '%s/%s' % (dataset_dir, filename)


def run(dataset_dir):
    """Runs the conversion operation.
    Args:
      dataset_dir: The dataset directory where the dataset is stored.
    """
    if not tf.gfile.Exists(dataset_dir):
        tf.gfile.MakeDirs(dataset_dir)

    training_filename = _get_output_filename(dataset_dir, 'train')
    testing_filename = _get_output_filename(dataset_dir, 'test')

    if tf.gfile.Exists(training_filename) and tf.gfile.Exists(testing_filename):
        print('Dataset files already exist. Exiting without re-creating them.')
        return

    # First, process the training data:
    with tf.python_io.TFRecordWriter(training_filename) as tfrecord_writer:
        data_filename = os.path.join(dataset_dir, _TRAIN_FILENAME)
        _add_to_tfrecord(data_filename, tfrecord_writer, augment=True)

    # Next, process the testing data:
    with tf.python_io.TFRecordWriter(testing_filename) as tfrecord_writer:
        data_filename = os.path.join(dataset_dir, _TEST_FILENAME)
        _add_to_tfrecord(data_filename, tfrecord_writer, augment=False)

    # Finally, write the labels file:
    labels_to_class_names = dict(zip(range(len(_CLASS_NAMES)), _CLASS_NAMES))
    dataset_utils.write_label_file(labels_to_class_names, dataset_dir)

    print('\nFinished converting the GTSRB dataset!')
