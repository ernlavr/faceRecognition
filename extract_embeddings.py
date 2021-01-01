# import the necessary packages
from imutils import paths
import numpy as np
import imutils
import pickle
from cv2 import cv2
import os
import time
import re

class EmbeddingExtractor():
  """Object for extracting facial embeddings which are used to train a ML model
    PARAMETERS
    ----------
    Dataset : str 
        Path to the input dataset. Images of faces which we want to extract embeddings of. Use .JPEG, .PNG or .JPG formats
        Should follow the structure
        Dataset/|
                + - NAME1/
                |   |
                |   + (Name1.PNG)
                |   |
                |   + (Name2.PNG)
                |
                + - NAME2/
                    |
                    + (Name1.PNG)
                    |
                    + (Name2.PNG)
    EmbeddingOutput : str
        Output location of where the serialized embeddings will be stored
    FaceDetector : str
        Caffe DNN Model for detecting faces
    EmbeddingModel : str
        Torch DNN Model for extracting facial embeddings
    """
  def __init__(self, Dataset: str, EmbeddingOutput: str, FaceDetector: str, EmbeddingModel: str):
    self._DATASET = Dataset
    self._EMBEDDING_OUTPUT = EmbeddingOutput
    self._DETECTOR = FaceDetector
    self._EMBEDDINGMODEL = EmbeddingModel

    caffeProtoPath = os.path.sep.join([self._DETECTOR, "deploy.prototxt"])
    caffeModelPath = os.path.sep.join([self._DETECTOR, "res10_300x300_ssd_iter_140000.caffemodel"])

    print("[INFO] loading face detector...")
    self.detector = cv2.dnn.readNetFromCaffe(caffeProtoPath, caffeModelPath)
    
    print("[INFO] loading face recognizer...")
    self.embedder = cv2.dnn.readNetFromTorch(self._EMBEDDINGMODEL)

  def ExtractEmbedding(self, image, startX: int, endX: int, startY: int, endY: int):
    """Extract 128-D vector of facial characteristics from the image's specified region
    PARAMETERS
    ----------
    image : NumPyArray uint8 
        Return value of loading an image using OpenCV imread()
    startX
        Start coordinate of X axis
    startY
        Start coordinate of Y axis
    endX
        End coordinate of X axis
    endY
        End coordinate of Y axis
    RETURNS
    -------
    ndarray(float32)
        Array of facial embeddings of the particular face
    """
    
    # Extract the face and grab the region-of-interest dimensions
    face = image[startY:endY, startX:endX]
    (fH, fW) = face.shape[:2]

    # ensure the face width and height are sufficiently large
    if fW < 20 or fH < 20:
      return None
    
    # Construct a blob for the face ROI, then pass the blob through our face
    # embedding model to obtain the 128-d quantification
    faceBlob =  cv2.dnn.blobFromImage(face, 1.0 / 255,
      (96, 96), (0, 0, 0), swapRB=True, crop=False)
    self.embedder.setInput(faceBlob)
    return self.embedder.forward()

  def GetConfidence(self, detections, element):
    return detections[0, 0, element, 2]

  def GetImage(self, imagePath: str):
    """
      Get a numpy array representing an image that is scaled to 600 pixels
      Parameters
      ----------
      imagePath : str
          Path to the image
      Returns
      -------
      ndarray(uint8)
          Image representation
    """
    # Load the image, resize it to have a width of 600 pixels (while
    # maintaining the aspect ratio), and then grab the image dimensions
    image = cv2.imread(imagePath)
    return imutils.resize(image, width=600)

  def ProcessFolders(self, imageFolder):
    """
      Recursively scan through a folder and create serialized dict object of facial embeddings and labels for all photos found.
      Labels are taken from sub-directory names
      Parameters
      ----------
      imageFolder : str
          Path to a folder containing all of the dataset
    """
    # Get the image paths from the Dataset folder
    print("[INFO] quantifying faces...")
    imagePaths = list(paths.list_images(self._DATASET))

    # Initialize our lists of extracted facial embeddings, corresponding people names
    # and total number of faces processed
    knownEmbeddings = []
    knownNames = []
    total = 1

    # Loop over the image paths
    for (i, imagePath) in enumerate(imagePaths):
      # Extract the person name from the image path
      print("[INFO] processing image {}/{}".format(i + 1, len(imagePaths)))
      success = self.ProcessImage(imagePath)
      if success == None:
        print("[INFO] Image processing failed for path: ", imagePath)
        continue
      else:
        (vec, name) = success
        knownNames.append(name)
        knownEmbeddings.append(vec.flatten())
        total += 1      # Extract the person name from the image path

    # dump the facial embeddings + names to disk
    print("[INFO] serializing {} encodings...".format(total))
    data = {"embeddings": knownEmbeddings, "names": knownNames}
    f = open(self._EMBEDDING_OUTPUT, "wb")
    f.write(pickle.dumps(data))
    f.close()

  
  def ProcessImage(self, imagePath):
    """
      Read and process an image by detecting the location of the face using Caffe DNN face detector
      and Torch DNN for generating facial embeddings
      PARAMETERS
      ----------
      imagePath : str
          Path to the image
      RETURNS
      -------
      ndarray(float32)
          Image facial embeddings
      Str
          Label of the facial embedding
    """
    # Extract the name of the image
    name = imagePath.split(os.path.sep)[-2]
    # Get an OpenCV representation of the image
    image = self.GetImage(imagePath)
    (h, w) = image.shape[:2]

    # Construct a blob from the image
    imageBlob = cv2.dnn.blobFromImage(
     cv2.resize(image, (300, 300)), 1.0, (300, 300),
      (104.0, 177.0, 123.0), swapRB=False, crop=False)

    # Apply Caffe face detector to localize faces in the input image
    self.detector.setInput(imageBlob)
    detections = self.detector.forward()

    # ensure at least one face was found
    if len(detections) > 0:
      i = np.argmax(detections[0, 0, :, 2])
      confidence = self.GetConfidence(detections, i)
      
      # Ensure that the detection with the largest probability also
      # means our minimum probability test (thus helping filter out
      # weak detections)
      if confidence > 0.5:
        # Compute the (x, y)-coordinates of the bounding box for the face
        box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
        (startX, startY, endX, endY) = box.astype("int")

        # Use Torch to extract the embedding
        vec = self.ExtractEmbedding(image, startX, endX, startY, endY)
        if vec is None:
          return None

        return vec, name


