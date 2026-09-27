import { readFileSync, realpathSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

// Use OpenClaw's credential resolver. Never copy keys into Wiki configuration or stdout.
export function openClawGoogleKey({ agentId='wiki', packageDir=join(realpathSync(join(homedir(),'.openclaw/tools/node')), 'lib/node_modules/openclaw') } = {}) {
  if (!/^[a-zA-Z0-9_-]+$/u.test(agentId)) throw new Error('Invalid agent ID');
  let pending;
  return async () => {
    pending ??= (async () => {
      const sdk=await import(pathToFileURL(join(packageDir,'dist/plugin-sdk/agent-runtime.js')).href);
      const cfg=JSON.parse(readFileSync(join(homedir(),'.openclaw/openclaw.json'),'utf8'));
      if (!cfg.agents?.entries?.[agentId]) throw new Error('OpenClaw agent not configured');
      const agentDir=cfg.agents.entries[agentId].agentDir ?? join(homedir(),'.openclaw/agents',agentId,'agent');
      const store=sdk.ensureAuthProfileStore(agentDir);
      const profiles=Object.entries(store.profiles).filter(([,v])=>v.provider==='google');
      if(profiles.length!==1) throw new Error('Select one Google credential profile');
      const auth=await sdk.resolveApiKeyForProfile({cfg,store,profileId:profiles[0][0],agentDir});
      if(!auth?.apiKey) throw new Error('Google credential unavailable');
      return auth.apiKey;
    })();
    return pending;
  };
}
