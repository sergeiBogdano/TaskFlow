import { useEffect, useRef, useState } from 'react';

export function useAssistantVoice(onText: (text: string) => void) {
  const [listening, setListening] = useState(false);
  const [error, setError] = useState('');
  const active = useRef<any>(null);
  const callback = useRef(onText); callback.current = onText;
  useEffect(() => () => active.current?.abort(), []);
  const toggle = () => {
    if (active.current) { active.current.stop(); return; }
    const Recognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!Recognition) { setError('Распознавание речи недоступно в этом браузере. Введите запрос текстом.'); return; }
    if (!window.isSecureContext) { setError('Для микрофона нужен HTTPS или localhost. Текстовый ввод доступен.'); return; }
    setError('');
    const recognition = new Recognition(); active.current = recognition;
    recognition.lang = 'ru-RU'; recognition.interimResults = false;
    recognition.onstart = () => setListening(true);
    recognition.onend = () => { setListening(false); active.current = null; };
    recognition.onerror = () => { setError('Не удалось распознать речь. Проверьте разрешение на микрофон.'); setListening(false); active.current = null; };
    recognition.onresult = (event: any) => { const text = event.results?.[0]?.[0]?.transcript; if (text) callback.current(text); };
    try { recognition.start(); } catch { active.current = null; setError('Микрофон недоступен. Введите запрос текстом.'); }
  };
  return { listening, error, toggle };
}
