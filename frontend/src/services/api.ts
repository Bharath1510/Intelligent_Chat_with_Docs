import axios from 'axios';

const API_BASE_URL = '/api/v1';

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export function streamChatQuery(
  sessionId: string,
  query: string,
  docIds: string[] | undefined,
  onToken: (token: string) => void,
  onCitations: (citations: any[]) => void,
  onDone: () => void,
  onError: (err: any) => void
) {
  let url = `${API_BASE_URL}/chat/stream?session_id=${encodeURIComponent(sessionId)}&query=${encodeURIComponent(query)}`;
  if (docIds && docIds.length > 0) {
    url += `&doc_ids=${encodeURIComponent(docIds.join(','))}`;
  }

  let doneEmitted = false;

  fetch(url)
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(`Stream HTTP error! Status: ${response.status}`);
      }
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) return;

      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.replace('data: ', '').trim();
            try {
              const data = JSON.parse(dataStr);
              if (data.type === 'token') {
                onToken(data.content);
              } else if (data.type === 'citations') {
                onCitations(data.content);
              } else if (data.type === 'done') {
                if (!doneEmitted) {
                  doneEmitted = true;
                  onDone();
                }
              }
            } catch (e) {
              // Ignore non-JSON line
            }
          }
        }
      }

      // Only call onDone if we haven't received a done event from the stream
      if (!doneEmitted) {
        doneEmitted = true;
        onDone();
      }
    })
    .catch((err) => {
      onError(err);
    });
}
