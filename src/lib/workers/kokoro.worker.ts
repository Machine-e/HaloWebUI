let tts: any;
let isInitialized = false; // Flag to track initialization status
const DEFAULT_MODEL_ID = 'onnx-community/Kokoro-82M-v1.0-ONNX'; // Default model
let runtimePromise: Promise<{
	KokoroTTS: {
		from_pretrained: (modelId: string, options: Record<string, unknown>) => Promise<any>;
	};
}> | null = null;

const ensureRuntime = async () => {
	if (!runtimePromise) {
		runtimePromise = Promise.all([import('@huggingface/transformers'), import('kokoro-js')]).then(
			([transformers, kokoro]) => {
				transformers.env.backends.onnx.wasm.wasmPaths = '/wasm/';
				return { KokoroTTS: kokoro.KokoroTTS };
			}
		);
	}

	return runtimePromise;
};

self.onmessage = async (event) => {
	const { type, payload } = event.data;

	if (type === 'init') {
		let { model_id, dtype } = payload;
		model_id = model_id || DEFAULT_MODEL_ID; // Use default model if none provided

		self.postMessage({ status: 'init:start' });

		try {
			const { KokoroTTS } = await ensureRuntime();
			tts = await KokoroTTS.from_pretrained(model_id, {
				dtype,
				device: !!navigator?.gpu ? 'webgpu' : 'wasm' // Detect WebGPU
			});
			isInitialized = true; // Mark as initialized after successful loading
			self.postMessage({ status: 'init:complete' });
		} catch (error) {
			isInitialized = false; // Ensure it's marked as false on failure
			self.postMessage({
				status: 'init:error',
				error: error instanceof Error ? error.message : String(error)
			});
		}
	}

	if (type === 'generate') {
		if (!isInitialized || !tts) {
			// Ensure model is initialized
			self.postMessage({ status: 'generate:error', error: 'TTS model not initialized' });
			return;
		}

		const { text, voice } = payload;
		self.postMessage({ status: 'generate:start' });

		try {
			const rawAudio = await tts.generate(text, { voice });
			const blob = await rawAudio.toBlob();
			const blobUrl = URL.createObjectURL(blob);
			self.postMessage({ status: 'generate:complete', audioUrl: blobUrl });
		} catch (error) {
			self.postMessage({
				status: 'generate:error',
				error: error instanceof Error ? error.message : String(error)
			});
		}
	}

	if (type === 'status') {
		// Respond with the current initialization status
		self.postMessage({ status: 'status:check', initialized: isInitialized });
	}
};
