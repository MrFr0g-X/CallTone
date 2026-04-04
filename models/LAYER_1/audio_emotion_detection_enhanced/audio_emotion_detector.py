"""
Audio emotion detection using nvidia/Audio2Emotion-v3.0 model or alternatives.

This module provides emotion detection for audio segments extracted from 
speaker diarization results.

Supports:
- NVIDIA Audio2Emotion-v3.0 (ONNX-based, works offline)
- HuggingFace wav2vec2 emotion models (open-source fallback)
"""

import os
import warnings
import numpy as np
import torch
import torchaudio
from pathlib import Path
from typing import List, Dict, Tuple, Optional


class Audio2EmotionDetector:
    """
    Detector for audio-based emotion recognition.
    
    Supports multiple backends:
    1. NVIDIA Audio2Emotion-v3.0 (ONNX runtime)
    2. HuggingFace Wav2Vec2 emotion models
    """
    
    def __init__(
        self, 
        model_dir: str = None, 
        device: str = None,
        backend: str = "auto"
    ):
        """
        Initialize the emotion detector.
        
        Args:
            model_dir: Path to model directory
            device: Device to run on ('cuda' or 'cpu'). Auto-detects if None.
            backend: "onnx", "huggingface", or "auto" (default)
        """
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.backend = backend
        self.model = None
        self.processor = None
        self.onnx_session = None
        
        # Emotion labels for NVIDIA model
        self.emotion_labels = [
            "anger", "disgust", "fear", "joy", "neutral", "sadness"
        ]
        
        # Try to load ONNX model (NVIDIA)
        if backend == "auto" or backend == "onnx":
            try:
                self._load_onnx_model(model_dir)
                self.backend = "onnx"
                return
            except Exception as e:
                if backend == "onnx":
                    raise
                warnings.warn(f"Could not load ONNX model: {e}. Falling back to HuggingFace...")
        
        # Fallback to HuggingFace model
        if backend == "auto" or backend == "huggingface":
            try:
                self._load_huggingface_model()
                self.backend = "huggingface"
                return
            except Exception as e:
                if backend == "huggingface":
                    raise
                warnings.warn(f"Could not load HuggingFace model: {e}")
        
        raise RuntimeError(
            "Could not load any emotion detection model. "
            "Please run setup.sh to install dependencies."
        )
    
    def _load_onnx_model(self, model_dir: str = None):
        """Load NVIDIA Audio2Emotion ONNX model."""
        if model_dir is None:
            model_dir = os.path.join(
                os.path.dirname(__file__),
                "models",
                "Audio2Emotion-v3.0"
            )
        
        self.model_dir = Path(model_dir)
        
        if not self.model_dir.exists():
            raise FileNotFoundError(
                f"Model directory not found: {self.model_dir}\n"
                f"Please download the model first using download_model.py"
            )
        
        # Look for ONNX file
        onnx_file = self.model_dir / "network.onnx"
        if not onnx_file.exists():
            raise FileNotFoundError(
                f"ONNX model file not found: {onnx_file}\n"
                f"Expected network.onnx in {self.model_dir}"
            )
        
        print(f"Loading Audio2Emotion ONNX model from {self.model_dir}")
        print(f"Using device: {self.device}")
        
        try:
            import onnxruntime as ort
            
            # Create ONNX session
            providers = ['CUDAExecutionProvider', 'CPUExecutionProvider'] if self.device == 'cuda' else ['CPUExecutionProvider']
            self.onnx_session = ort.InferenceSession(str(onnx_file), providers=providers)
            
            # Get input/output names
            self.input_name = self.onnx_session.get_inputs()[0].name
            self.output_name = self.onnx_session.get_outputs()[0].name
            
            print("✓ Audio2Emotion ONNX model loaded successfully")
            print(f"  Model file: {onnx_file.name} ({onnx_file.stat().st_size / 1024**3:.2f} GB)")
            print(f"  Emotions: {', '.join(self.emotion_labels)}")
            
        except ImportError:
            raise ImportError(
                "onnxruntime not installed. Install with:\n"
                "  conda run -n calltone pip install onnxruntime-gpu  # for GPU\n"
                "  conda run -n calltone pip install onnxruntime      # for CPU"
            )
    
    def _load_huggingface_model(self):
        """Load HuggingFace wav2vec2 emotion model as fallback."""
        print("Loading HuggingFace emotion model")
        print(f"Using device: {self.device}")
        
        try:
            from transformers import Wav2Vec2ForSequenceClassification, Wav2Vec2Processor
            
            # Check for local model first (for offline operation)
            local_model_path = Path(__file__).parent / "models" / "wav2vec2-emotion"
            
            if local_model_path.exists():
                print(f"  Loading from local cache: {local_model_path}")
                model_name_or_path = str(local_model_path)
            else:
                # Download from HuggingFace (requires internet)
                model_name_or_path = "ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition"
                print(f"  Downloading from HuggingFace: {model_name_or_path}")
                print("  (This will be cached for future offline use)")
            
            self.processor = Wav2Vec2Processor.from_pretrained(model_name_or_path, local_files_only=local_model_path.exists())
            self.model = Wav2Vec2ForSequenceClassification.from_pretrained(model_name_or_path, local_files_only=local_model_path.exists())
            self.model.to(self.device)
            self.model.eval()
            
            # Update emotion labels for this model
            self.emotion_labels = [
                "angry", "calm", "disgust", "fearful", "happy", "neutral", "sad", "surprised"
            ]
            
            print("✓ HuggingFace emotion model loaded successfully")
            print(f"  Emotions: {', '.join(self.emotion_labels)}")
            
        except ImportError:
            raise ImportError(
                "transformers not installed. Install with:\n"
                "  conda run -n calltone pip install transformers"
            )
    
    def process_audio_segment(
        self,
        audio_path: str,
        start_time: float,
        end_time: float,
        sample_rate: int = 16000
    ) -> Dict[str, any]:
        """
        Process a single audio segment and detect emotions.
        
        Args:
            audio_path: Path to audio file
            start_time: Start time in seconds
            end_time: End time in seconds
            sample_rate: Target sample rate for model
            
        Returns:
            Dict with emotion predictions and confidence scores
        """
        # Load audio
        waveform, sr = torchaudio.load(audio_path)
        
        # Convert to mono if stereo
        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)
        
        # Extract segment
        start_sample = int(start_time * sr)
        end_sample = int(end_time * sr)
        segment = waveform[:, start_sample:end_sample]
        
        # Resample if needed
        if sr != sample_rate:
            resampler = torchaudio.transforms.Resample(sr, sample_rate)
            segment = resampler(segment)
        
        # Process based on backend
        if self.backend == "onnx":
            return self._process_onnx(segment, sample_rate)
        else:
            return self._process_huggingface(segment, sample_rate)
    
    def _process_onnx(self, segment: torch.Tensor, sample_rate: int) -> Dict:
        """Process with ONNX model (NVIDIA Audio2Emotion)."""
        # Prepare audio input
        audio_signal = segment.squeeze().cpu().numpy().astype(np.float32)
        
        # Normalize
        audio_signal = audio_signal / (np.max(np.abs(audio_signal)) + 1e-7)
        
        # NVIDIA Audio2Emotion model requires audio length to be multiple of 10,000 samples
        # Minimum length is 10,000 samples (0.625 seconds at 16kHz)
        MIN_LENGTH = 10000
        CHUNK_SIZE = 10000
        
        current_length = len(audio_signal)
        
        if current_length < MIN_LENGTH:
            # Pad short segments
            padding_needed = MIN_LENGTH - current_length
            audio_signal = np.pad(audio_signal, (0, padding_needed), mode='constant', constant_values=0)
        elif current_length % CHUNK_SIZE != 0:
            # Pad to next multiple of CHUNK_SIZE
            padding_needed = CHUNK_SIZE - (current_length % CHUNK_SIZE)
            audio_signal = np.pad(audio_signal, (0, padding_needed), mode='constant', constant_values=0)
        
        # ONNX expects batch dimension: [batch, samples]
        audio_input = np.expand_dims(audio_signal, axis=0)
        
        # Run inference
        outputs = self.onnx_session.run(
            [self.output_name],
            {self.input_name: audio_input}
        )
        
        logits = outputs[0]
        
        # Convert to torch for softmax
        logits_tensor = torch.from_numpy(logits)
        probs = torch.softmax(logits_tensor, dim=-1)
        
        # Get top emotion
        top_prob, top_idx = torch.max(probs, dim=-1)
        
        # Get all emotion scores
        emotion_scores = {}
        for idx, label in enumerate(self.emotion_labels):
            if idx < probs.shape[-1]:
                emotion_scores[label] = float(probs[0, idx])
        
        # Determine top emotion
        if top_idx.item() < len(self.emotion_labels):
            top_emotion = self.emotion_labels[top_idx.item()]
        else:
            top_emotion = f"emotion_{top_idx.item()}"
        
        return {
            "emotion": top_emotion,
            "confidence": float(top_prob),
            "all_scores": emotion_scores,
            "segment_duration": len(segment[0]) / sample_rate
        }
    
    def _process_huggingface(self, segment: torch.Tensor, sample_rate: int) -> Dict:
        """Process with HuggingFace model."""
        with torch.no_grad():
            # Prepare input
            inputs = self.processor(
                segment.squeeze().numpy(),
                sampling_rate=sample_rate,
                return_tensors="pt",
                padding=True
            )
            
            # Move to device
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            # Get predictions
            outputs = self.model(**inputs)
            logits = outputs.logits
            probs = torch.softmax(logits, dim=-1)
            
            # Get top emotion
            top_prob, top_idx = torch.max(probs, dim=-1)
            
            # Get all emotion scores
            emotion_scores = {}
            for idx, label in enumerate(self.emotion_labels):
                if idx < probs.shape[-1]:
                    emotion_scores[label] = float(probs[0, idx].cpu())
            
            # Determine top emotion
            if top_idx.item() < len(self.emotion_labels):
                top_emotion = self.emotion_labels[top_idx.item()]
            else:
                top_emotion = f"emotion_{top_idx.item()}"
            
            return {
                "emotion": top_emotion,
                "confidence": float(top_prob.cpu()),
                "all_scores": emotion_scores,
                "segment_duration": len(segment[0]) / sample_rate
            }
    
    def process_diarization_segments(
        self,
        audio_path: str,
        segments: List[Dict]
    ) -> List[Dict]:
        """
        Process all segments from diarization results.
        
        Args:
            audio_path: Path to audio file
            segments: List of segment dicts with 'start', 'end', 'speaker' keys
            
        Returns:
            List of segments with added emotion information
        """
        enriched_segments = []
        
        print(f"\nProcessing {len(segments)} segments for emotion detection...")
        
        for i, segment in enumerate(segments, 1):
            print(f"  [{i}/{len(segments)}] {segment['speaker']} "
                  f"[{segment['start']:.1f}s → {segment['end']:.1f}s]", end="\r")
            
            try:
                emotion_result = self.process_audio_segment(
                    audio_path,
                    segment['start'],
                    segment['end']
                )
                
                # Add emotion info to segment
                enriched_segment = segment.copy()
                enriched_segment['audio_emotion'] = emotion_result['emotion']
                enriched_segment['audio_emotion_confidence'] = emotion_result['confidence']
                enriched_segment['audio_emotion_scores'] = emotion_result['all_scores']
                
                enriched_segments.append(enriched_segment)
                
            except Exception as e:
                print(f"\n  Warning: Failed to process segment {i}: {e}")
                # Keep original segment without emotion
                enriched_segments.append(segment.copy())
        
        print(f"\n✓ Emotion detection complete for {len(enriched_segments)} segments")
        
        return enriched_segments


def detect_emotions_for_transcript(
    audio_path: str,
    segments: List[Dict],
    model_dir: str = None
) -> List[Dict]:
    """
    Convenience function to detect emotions for all segments.
    
    Args:
        audio_path: Path to audio file
        segments: List of diarization segments
        model_dir: Optional custom model directory
        
    Returns:
        Segments with emotion information added
    """
    detector = Audio2EmotionDetector(model_dir=model_dir)
    return detector.process_diarization_segments(audio_path, segments)


if __name__ == "__main__":
    # Test the emotion detector
    print("Audio2Emotion Detector Test")
    print("=" * 60)
    
    detector = Audio2EmotionDetector()
    print("\nModel loaded successfully!")
    print(f"Supported emotions: {', '.join(detector.emotion_labels)}")
