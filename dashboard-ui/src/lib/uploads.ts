const MAX_FILE = 10 * 1024 * 1024;
const TYPES = new Set(['png', 'jpg', 'jpeg', 'webp', 'gif', 'pdf', 'txt', 'csv', 'docx', 'xlsx', 'pptx', 'zip']);

export async function prepareUpload(file: File): Promise<File> {
  const extension = file.name.split('.').pop()?.toLowerCase() || '';
  if (!TYPES.has(extension)) throw new Error('Этот формат запрещён. Используйте изображения, PDF, TXT/CSV, офисные документы или ZIP.');
  if (!file.size) throw new Error('Файл пустой.');
  let result = file;
  if (['png', 'jpg', 'jpeg', 'webp'].includes(extension)) {
    if (file.size > 32 * 1024 * 1024) throw new Error('Исходное изображение должно быть меньше 32 МБ.');
    const bitmap = await createImageBitmap(file).catch(() => { throw new Error('Не удалось прочитать изображение.'); });
    try {
      if (bitmap.width * bitmap.height > 25_000_000) throw new Error('Изображение слишком большое: максимум 25 мегапикселей.');
      const scale = Math.min(1, 2560 / Math.max(bitmap.width, bitmap.height));
      const canvas = document.createElement('canvas');
      canvas.width = Math.max(1, Math.round(bitmap.width * scale)); canvas.height = Math.max(1, Math.round(bitmap.height * scale));
      const context = canvas.getContext('2d');
      if (!context) throw new Error('Сжатие изображений недоступно в браузере.');
      context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      const compressed = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, 'image/webp', 0.86));
      if (compressed && (compressed.size < file.size || scale < 1)) result = new File([compressed], file.name.replace(/\.[^.]+$/, '.webp'), { type: 'image/webp' });
    } finally { bitmap.close(); }
  }
  if (result.size > MAX_FILE) throw new Error('Файл после обработки должен быть не больше 10 МБ.');
  return result;
}
