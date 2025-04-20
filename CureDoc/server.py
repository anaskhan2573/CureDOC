from flask import Flask, render_template, request, jsonify
import os
import numpy as np
import cv2
from sklearn import svm
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import base64
from io import BytesIO
from PIL import Image  # Added this import

app = Flask(__name__)

# Configuration
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def load_dataset():
    """Load and preprocess dataset with better error handling"""
    dataset_path = 'dataset'
    images = []
    labels = []
    
    # Check if dataset directory exists
    if not os.path.exists(dataset_path):
        print(f"Dataset directory '{dataset_path}' not found!")
        return None, None, None, None

    # Check for tumor and no_tumor subdirectories
    for class_name in ['no_tumor', 'tumor']:
        class_path = os.path.join(dataset_path, class_name)
        if not os.path.exists(class_path):
            print(f"Class directory '{class_path}' not found!")
            continue
            
        for img_file in os.listdir(class_path):
            img_path = os.path.join(class_path, img_file)
            try:
                # Read and preprocess image
                img = cv2.imread(img_path)
                if img is None:
                    print(f"Could not read image: {img_path}")
                    continue
                    
                img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                img = cv2.resize(img, (64, 64))  # Resize to 64x64
                img = img / 255.0  # Normalize
                
                images.append(img.flatten())
                labels.append(0 if class_name == 'no_tumor' else 1)
            except Exception as e:
                print(f"Error processing {img_path}: {e}")

    if len(images) == 0:
        print("No valid images found in dataset!")
        return None, None, None, None

    X = np.array(images)
    y = np.array(labels)
    
    # Ensure we have enough samples for splitting
    if len(X) < 5:  # Minimum 5 samples needed
        print(f"Not enough samples ({len(X)}). Using all for training.")
        return X, None, y, None
    
    # Split into train/test
    return train_test_split(X, y, test_size=0.2, random_state=42)

def train_model(X_train, y_train):
    """Train SVM model with better parameters"""
    model = svm.SVC(
        kernel='rbf',
        C=10,  # Higher regularization
        gamma='scale',
        probability=True,
        random_state=42
    )
    model.fit(X_train, y_train)
    return model

# Load dataset and train model
X_train, X_test, y_train, y_test = load_dataset()

if X_train is None:
    print("Failed to load dataset. Using mock data...")
    # Create mock data
    X_train = np.random.rand(10, 4096)  # 64x64 = 4096 features
    y_train = np.random.randint(0, 2, 10)
    X_test = np.random.rand(3, 4096)
    y_test = np.random.randint(0, 2, 3)

model = train_model(X_train, y_train)

# Evaluate model
if X_test is not None:
    test_acc = accuracy_score(y_test, model.predict(X_test))
    print(f"Test Accuracy: {test_acc:.2f}")
else:
    train_acc = accuracy_score(y_train, model.predict(X_train))
    print(f"Train Accuracy: {train_acc:.2f} (no test set)")

def preprocess_image(filepath):
    """Improved image preprocessing with error handling"""
    try:
        img = cv2.imread(filepath)
        if img is None:
            raise ValueError("Could not read image file")
            
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        img = cv2.resize(img, (64, 64))
        img = img / 255.0
        return img.flatten()
    except Exception as e:
        print(f"Image processing error: {e}")
        return None

@app.route('/')
def home():
    return render_template('NeuroScan.html', 
                         train_samples=len(X_train),
                         test_samples=len(X_test) if X_test is not None else 0)

@app.route('/classify', methods=['POST'])
def classify():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file:
        try:
            # Save file temporarily
            filename = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filename)
            
            # Preprocess image
            img_vector = preprocess_image(filename)
            if img_vector is None:
                return jsonify({'error': 'Invalid image format'}), 400
            
            # Make prediction
            prediction = model.predict([img_vector])[0]
            confidence = model.predict_proba([img_vector])[0][prediction] * 100
            label = "Tumor" if prediction == 1 else "No Tumor"
            
            # Prepare image for display
            img = cv2.imread(filename)
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(img)  # Now using the imported Image class
            img.thumbnail((300, 300))
            buffered = BytesIO()
            img.save(buffered, format="JPEG")
            img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
            
            # Clean up
            os.remove(filename)
            
            return jsonify({
                'prediction': label,
                'confidence': round(confidence, 2),
                'image': img_str
            })
        except Exception as e:
            print(f"Classification error: {e}")
            return jsonify({'error': str(e)}), 500
    
    return jsonify({'error': 'Invalid file'}), 400

if __name__ == '__main__':
    app.run(debug=True, port=5010)