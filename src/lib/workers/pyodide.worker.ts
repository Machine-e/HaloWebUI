import { loadPyodide, type PyodideInterface } from 'pyodide';

declare global {
	interface Window {
		stdout: string | null;
		stderr: string | null;
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		result: any;
		pyodide: PyodideInterface;
		packages: string[];
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		[key: string]: any;
	}
}

type GeneratedFile = {
	name: string;
	path: string;
	size: number;
	content_base64: string;
};

type GeneratedFilesCollection = {
	files: GeneratedFile[];
	warnings: string[];
};

const GENERATED_WORKSPACE_ROOT = '/mnt/generated';
const DATA_WORKSPACE_ROOT = '/mnt/data';
const MAX_GENERATED_FILES = 20;
const MAX_GENERATED_FILE_BYTES = 25 * 1024 * 1024;
const MAX_GENERATED_TOTAL_BYTES = 50 * 1024 * 1024;

const ensureDirectory = (path: string) => {
	try {
		self.pyodide.FS.stat(path);
	} catch {
		self.pyodide.FS.mkdirTree(path);
	}
};

const normalizeRelativePath = (path: string) =>
	path
		.split('/')
		.filter((part) => part && part !== '.')
		.join('/');

const uint8ArrayToBase64 = (data: Uint8Array) => {
	const chunkSize = 0x8000;
	let binary = '';
	for (let offset = 0; offset < data.length; offset += chunkSize) {
		binary += String.fromCharCode(...data.subarray(offset, offset + chunkSize));
	}
	return btoa(binary);
};

const collectGeneratedFiles = (
	roots: { root: string; prefix?: string }[]
): GeneratedFilesCollection => {
	const files: GeneratedFile[] = [];
	const warnings: string[] = [];
	let totalBytes = 0;

	const walk = (root: string, current: string, prefix = '') => {
		if (files.length >= MAX_GENERATED_FILES) {
			return;
		}

		let entries: string[] = [];
		try {
			entries = self.pyodide.FS.readdir(current).filter(
				(entry: string) => entry !== '.' && entry !== '..'
			);
		} catch {
			return;
		}

		for (const entry of entries) {
			if (files.length >= MAX_GENERATED_FILES) {
				if (!warnings.includes('Generated file count limit reached.')) {
					warnings.push('Generated file count limit reached.');
				}
				return;
			}

			const fullPath = `${current}/${entry}`.replace(/\/+/g, '/');
			let stat;
			try {
				stat = self.pyodide.FS.stat(fullPath);
			} catch {
				continue;
			}

			if (self.pyodide.FS.isDir(stat.mode)) {
				walk(root, fullPath, prefix);
				continue;
			}

			if (!self.pyodide.FS.isFile(stat.mode) || stat.size < 0) {
				continue;
			}

			const relativePath = normalizeRelativePath(
				`${prefix ? `${prefix}/` : ''}${fullPath.slice(root.length).replace(/^\/+/, '')}`
			);
			if (!relativePath || relativePath.split('/').includes('..')) {
				continue;
			}

			if (stat.size > MAX_GENERATED_FILE_BYTES) {
				warnings.push(`Skipped oversized generated file: ${relativePath}`);
				continue;
			}
			if (totalBytes + stat.size > MAX_GENERATED_TOTAL_BYTES) {
				warnings.push(`Skipped generated file after total size limit: ${relativePath}`);
				continue;
			}

			const data = self.pyodide.FS.readFile(fullPath) as Uint8Array;
			const copy = new Uint8Array(data.length);
			copy.set(data);
			totalBytes += copy.byteLength;
			files.push({
				name: relativePath.split('/').pop() ?? 'generated-file',
				path: relativePath,
				size: copy.byteLength,
				content_base64: uint8ArrayToBase64(copy)
			});
		}
	};

	for (const { root, prefix } of roots) {
		walk(root, root, prefix);
	}

	return { files, warnings };
};

async function loadPyodideAndPackages(packages: string[] = []) {
	self.stdout = null;
	self.stderr = null;
	self.result = null;

	self.pyodide = await loadPyodide({
		indexURL: APP_PYODIDE_INDEX_URL,
		stdout: (text) => {
			console.log('Python output:', text);

			if (self.stdout) {
				self.stdout += `${text}\n`;
			} else {
				self.stdout = `${text}\n`;
			}
		},
		stderr: (text) => {
			console.log('An error occurred:', text);
			if (self.stderr) {
				self.stderr += `${text}\n`;
			} else {
				self.stderr = `${text}\n`;
			}
		},
		packages: ['micropip']
	});

	let mountDir = '/mnt';
	self.pyodide.FS.mkdirTree(mountDir);

	// Create writable directories for user uploads and downloadable outputs.
	self.pyodide.FS.mkdirTree('/mnt/uploads');
	self.pyodide.FS.mkdirTree(GENERATED_WORKSPACE_ROOT);
	self.pyodide.FS.mkdirTree(DATA_WORKSPACE_ROOT);
	// self.pyodide.FS.mount(self.pyodide.FS.filesystems.IDBFS, {}, mountDir);

	// // Load persisted files from IndexedDB (Initial Sync)
	// await new Promise<void>((resolve, reject) => {
	// 	self.pyodide.FS.syncfs(true, (err) => {
	// 		if (err) {
	// 			console.error('Error syncing from IndexedDB:', err);
	// 			reject(err);
	// 		} else {
	// 			console.log('Successfully loaded from IndexedDB.');
	// 			resolve();
	// 		}
	// 	});
	// });

	const micropip = self.pyodide.pyimport('micropip');

	// await micropip.set_index_urls('https://pypi.org/pypi/{package_name}/json');
	await micropip.install(packages);
}

self.onmessage = async (event) => {
	const { id, code, ...context } = event.data;

	// Handle file upload messages
	if (event.data.type === 'upload') {
		const { filename, content } = event.data;
		if (!self.pyodide) {
			await loadPyodideAndPackages([]);
		}
		try {
			self.pyodide.FS.writeFile('/mnt/uploads/' + filename, new Uint8Array(content));
			self.postMessage({ type: 'uploadResult', filename, success: true });
		} catch (e) {
			self.postMessage({
				type: 'uploadResult',
				filename,
				success: false,
				error: e instanceof Error ? e.message : String(e)
			});
		}
		return;
	}

	console.log(event.data);

	// The worker copies the context in its own "memory" (an object mapping name to values)
	for (const key of Object.keys(context)) {
		self[key] = context[key];
	}

	// make sure loading is done
	await loadPyodideAndPackages(self.packages);

	const workDir = `${GENERATED_WORKSPACE_ROOT}/${String(id || 'run').replace(/[^a-zA-Z0-9_-]/g, '')}`;
	ensureDirectory(workDir);
	const previousCwd = (self.pyodide.FS as any).cwd();

	try {
		(self.pyodide.FS as any).chdir(workDir);

		// check if matplotlib is imported in the code
		if (code.includes('matplotlib')) {
			// Override plt.show() to return base64 image
			await self.pyodide.runPythonAsync(`import base64
import os
from io import BytesIO

# before importing matplotlib
# to avoid the wasm backend (which needs js.document', not available in worker)
os.environ["MPLBACKEND"] = "AGG"

import matplotlib.pyplot

_old_show = matplotlib.pyplot.show
assert _old_show, "matplotlib.pyplot.show"

def show(*, block=None):
	buf = BytesIO()
	matplotlib.pyplot.savefig(buf, format="png")
	buf.seek(0)
	# encode to a base64 str
	img_str = base64.b64encode(buf.read()).decode('utf-8')
	matplotlib.pyplot.clf()
	buf.close()
	print(f"data:image/png;base64,{img_str}")

matplotlib.pyplot.show = show`);
		}

		self.result = await self.pyodide.runPythonAsync(code);

		// Safely process and recursively serialize the result
		self.result = processResult(self.result);

		console.log('Python result:', self.result);

		// Persist any changes to IndexedDB
		// await new Promise<void>((resolve, reject) => {
		// 	self.pyodide.FS.syncfs(false, (err) => {
		// 		if (err) {
		// 			console.error('Error syncing to IndexedDB:', err);
		// 			reject(err);
		// 		} else {
		// 			console.log('Successfully synced to IndexedDB.');
		// 			resolve();
		// 		}
		// 	});
		// });
	} catch (error) {
		self.stderr = error instanceof Error ? error.message : String(error);
	} finally {
		try {
			(self.pyodide.FS as any).chdir(previousCwd);
		} catch {
			(self.pyodide.FS as any).chdir('/');
		}
	}

	const { files: generatedFiles, warnings: fileWarnings } = collectGeneratedFiles([
		{ root: workDir },
		{ root: DATA_WORKSPACE_ROOT }
	]);
	(self as any).postMessage({
		id,
		result: self.result,
		stdout: self.stdout,
		stderr: self.stderr,
		generated_files: generatedFiles,
		file_warnings: fileWarnings
	});
};

function processResult(result: any): any {
	// Catch and always return JSON-safe string representations
	try {
		if (result == null) {
			// Handle null and undefined
			return null;
		}
		if (typeof result === 'string' || typeof result === 'number' || typeof result === 'boolean') {
			// Handle primitive types directly
			return result;
		}
		if (typeof result === 'bigint') {
			// Convert BigInt to a string for JSON-safe representation
			return result.toString();
		}
		if (Array.isArray(result)) {
			// If it's an array, recursively process items
			return result.map((item) => processResult(item));
		}
		if (typeof result.toJs === 'function') {
			// If it's a Pyodide proxy object (e.g., Pandas DF, Numpy Array), convert to JS and process recursively
			return processResult(result.toJs());
		}
		if (typeof result === 'object') {
			// Convert JS objects to a recursively serialized representation
			const processedObject: { [key: string]: any } = {};
			for (const key in result) {
				if (Object.prototype.hasOwnProperty.call(result, key)) {
					processedObject[key] = processResult(result[key]);
				}
			}
			return processedObject;
		}
		// Stringify anything that's left (e.g., Proxy objects that cannot be directly processed)
		return JSON.stringify(result);
	} catch (err) {
		// In case something unexpected happens, we return a stringified fallback
		return `[processResult error]: ${err instanceof Error ? err.message : String(err)}`;
	}
}

export default {};
