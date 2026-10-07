// Only these Feishu APIs are used; article URLs and provider error bodies are never followed/logged.
export function resolveWikiFeishuAccount(hostConfig,accountId,{explicit=false}={}){
 const channel=hostConfig.channels?.feishu;
 if(!explicit)return {...channel,...channel?.accounts?.[accountId]};
 const account=channel?.accounts?.[accountId]??(accountId==='default'?channel:undefined);
 if(!account)throw Error('Selected Feishu account unavailable');
 return {...account,...(channel?.enabled===false?{enabled:false}:{}),...(!account.domain&&channel?.domain?{domain:channel.domain}:{})};
}

export function createFeishuClient({ credentials, fetchImpl = fetch, timeoutMs = 10000 }) {
  let token, expires = 0;
  async function request(path, body, bearer, parentSignal) {
    const signal = AbortSignal.any([AbortSignal.timeout(timeoutMs), ...(parentSignal ? [parentSignal] : [])]);
    try {
      const response = await fetchImpl('https://open.feishu.cn/open-apis/' + path, {
        method: body ? 'POST' : 'GET', redirect: 'error', signal,
        headers: { 'Content-Type': 'application/json', ...(bearer ? { Authorization: 'Bearer ' + bearer } : {}) },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      if (!response.ok || !response.body) throw new Error('Unavailable');
      const chunks = []; let size = 0;
      for await (const chunk of response.body) {
        size += chunk.byteLength;
        if (size > 131072) throw new Error('Too large');
        chunks.push(Buffer.from(chunk));
      }
      const value = JSON.parse(Buffer.concat(chunks).toString('utf8'));
      if (value.code !== 0) throw new Error('Rejected');
      return value;
    } catch { throw new Error('Feishu request failed or result unknown'); }
  }
  async function auth(signal) {
    if (token && Date.now() < expires) return token;
    const value = credentials();
    if (typeof value.appId !== 'string' || !value.appId || typeof value.appSecret !== 'string' || !value.appSecret) {
      throw new Error('Resolved Feishu credentials required');
    }
    const response = await request('auth/v3/tenant_access_token/internal', { app_id: value.appId, app_secret: value.appSecret }, null, signal);
    if (typeof response.tenant_access_token !== 'string' || !Number.isFinite(response.expire)) throw new Error('Feishu authentication unavailable');
    token = response.tenant_access_token; expires = Date.now() + Math.max(0, response.expire - 60) * 1000;
    return token;
  }
  function messageId(id) {
    if (typeof id !== 'string' || !/^om_[\w-]+$/u.test(id)) throw new Error('Invalid Feishu message ID');
    return id;
  }
  return {
    async getMessage(id, { signal } = {}) {
      const path = 'im/v1/messages/' + messageId(id) + '?user_id_type=open_id';
      const value = await request(path, null, await auth(signal), signal);
      if (value.data?.items?.length !== 1) throw new Error('Single original message required');
      return value.data.items[0];
    },
    async send({ chatId, text, uuid }, { signal } = {}) {
      if (typeof chatId !== 'string' || !/^oc_[\w-]+$/u.test(chatId) || typeof text !== 'string' || !text || text.length > 4000 || !/^[a-f0-9]{32}$/u.test(uuid)) throw new Error('Invalid Feishu notification');
      const value = await request('im/v1/messages?receive_id_type=chat_id',
        { receive_id: chatId, msg_type: 'text', content: JSON.stringify({ text }), uuid }, await auth(signal), signal);
      return value.data;
    },
    async reply({ replyTo, text, uuid }, { signal } = {}) {
      const path = 'im/v1/messages/' + messageId(replyTo) + '/reply';
      const value = await request(path, { msg_type: 'text', content: JSON.stringify({ text }), uuid }, await auth(signal), signal);
      return value.data;
    },
  };
}
