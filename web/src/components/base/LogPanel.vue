<template>
  <div>
    <div class="card">
      <div class="card-body">
        <div class="d-flex align-items-center mb-3" style="gap:12px">
          <h5 class="mb-0">Runtime Logs</h5>
          <div class="ml-auto"></div>
          <button @click="openDiscordModal" class="btn btn-sm btn--outline" title="Connect Discord Webhook">
            <font-awesome-icon :icon="['fa-brands','fa-discord']" v-if="hasDiscordIcon" />
            <span>{{ discordConfigured ? 'Discord: ON' : 'Connect Discord Webhook' }}</span>
          </button>
          <button @click="toggleAutoLog" class="btn btn-sm" :class="autoLog ? 'btn--primary' : 'btn--outline'">
            <font-awesome-icon :icon="autoLog ? 'fa-regular fa-circle-play' : 'fa-regular fa-circle-pause'" />
            <span>Auto-refresh: {{ autoLog ? 'ON' : 'OFF' }}</span>
          </button>
        </div>
        <div class="crt-slab">
          <textarea id="scroll_text" disabled :placeholder="logContent" class="form-control crt-text log-textarea" aria-label="With textarea">{{logContent}}</textarea>
        </div>
      </div>
    </div>

    <div v-if="showDiscordModal" class="discord-modal-backdrop" @click.self="closeDiscordModal">
      <div class="discord-modal">
        <h5 class="mb-3">Connect Discord Webhook</h5>
        <div class="mb-2">
          <label class="form-label">Webhook URL</label>
          <input type="text" class="form-control" v-model="discordWebhookUrl" placeholder="https://discord.com/api/webhooks/..." />
        </div>
        <div class="mb-2">
          <label class="form-label">User ID to ping (optional)</label>
          <input type="text" class="form-control" v-model="discordUserId" placeholder="e.g. 123456789012345678" />
          <small class="text-muted">Pinged when a career run finishes. Leave blank to disable pings.</small>
        </div>
        <div v-if="discordMessage" class="mt-2" :class="discordMessageClass">{{ discordMessage }}</div>
        <div class="d-flex justify-content-end mt-3" style="gap:8px">
          <button class="btn btn-sm btn--outline" @click="testDiscord" :disabled="discordSaving">Test</button>
          <button class="btn btn-sm btn--outline" @click="closeDiscordModal" :disabled="discordSaving">Cancel</button>
          <button class="btn btn-sm btn--primary" @click="saveDiscord" :disabled="discordSaving">Save</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: "LogPanel",
  props: ['logContent', 'autoLog', 'toggleAutoLog'],
  data(){
    return{
      autoScroll: true,
      showDiscordModal: false,
      discordWebhookUrl: '',
      discordUserId: '',
      discordConfigured: false,
      discordSaving: false,
      discordMessage: '',
      discordMessageClass: '',
      hasDiscordIcon: false,
    }
  },
  mounted(){
    this.loadDiscordConfig();
  },
  methods: {
    loadDiscordConfig(){
      this.axios.get('/api/discord-config').then(res => {
        const d = res.data || {};
        this.discordWebhookUrl = d.webhook_url || '';
        this.discordUserId = d.user_id || '';
        this.discordConfigured = !!(d.webhook_url && d.webhook_url.length > 0);
      }).catch(() => {});
    },
    openDiscordModal(){
      this.discordMessage = '';
      this.showDiscordModal = true;
    },
    closeDiscordModal(){
      this.showDiscordModal = false;
    },
    saveDiscord(){
      this.discordSaving = true;
      this.discordMessage = '';
      const payload = { webhook_url: this.discordWebhookUrl, user_id: this.discordUserId };
      this.axios.post('/api/discord-config', payload).then(res => {
        const ok = res && res.data && res.data.status === 'ok';
        if (ok){
          this.discordConfigured = !!(this.discordWebhookUrl && this.discordWebhookUrl.length > 0);
          this.discordMessage = 'Saved.';
          this.discordMessageClass = 'text-success';
          setTimeout(() => { this.closeDiscordModal(); }, 600);
        } else {
          this.discordMessage = 'Save failed.';
          this.discordMessageClass = 'text-danger';
        }
      }).catch(err => {
        this.discordMessage = 'Save failed: ' + (err && err.message ? err.message : 'error');
        this.discordMessageClass = 'text-danger';
      }).finally(() => {
        this.discordSaving = false;
      });
    },
    testDiscord(){
      this.discordSaving = true;
      this.discordMessage = 'Saving then sending test…';
      this.discordMessageClass = '';
      const payload = { webhook_url: this.discordWebhookUrl, user_id: this.discordUserId };
      this.axios.post('/api/discord-config', payload).then(() => {
        return this.axios.post('/api/discord-test', {});
      }).then(res => {
        const ok = res && res.data && res.data.status === 'ok';
        this.discordMessage = ok ? 'Test sent. Check your Discord channel.' : ('Test failed: ' + (res && res.data && res.data.message || 'unknown'));
        this.discordMessageClass = ok ? 'text-success' : 'text-danger';
      }).catch(err => {
        this.discordMessage = 'Test failed: ' + (err && err.message ? err.message : 'error');
        this.discordMessageClass = 'text-danger';
      }).finally(() => {
        this.discordSaving = false;
      });
    },
  },
  updated(){
    if (this.autoScroll){
      const textarea = document.getElementById('scroll_text');
      if (textarea) textarea.scrollTop = textarea.scrollHeight;
    }
  }
}
</script>

<style scoped>
textarea{min-height:600px;font-size:12px;line-height:1.35}
.form-control:disabled{background:var(--surface-2)}
.card{display:block}
.card-body{display:block}
.crt-slab{position:relative;border-radius:12px;overflow:hidden;padding:8px}
.crt-slab:before{content:"";position:absolute;inset:0;background:repeating-linear-gradient(0deg, rgba(255,255,255,.05) 0, rgba(255,255,255,.05) 1px, transparent 2px, transparent 4px);opacity:.08;pointer-events:none}
.crt-slab:after{content:"";position:absolute;inset:0;background:radial-gradient(120% 80% at 50% 0%, color-mix(in srgb, var(--accent) 18%, transparent), transparent 60%);mix-blend-mode:screen;opacity:.3;pointer-events:none}
.crt-text{font-family:'Share Tech Mono',ui-monospace,Consolas,Monaco,monospace;color:#E6E6E6;text-shadow:0 0 6px color-mix(in srgb, var(--accent) 25%, transparent)}
.log-textarea{display:block;width:100%;min-height:70vh;border:1px solid var(--accent);border-radius:var(--radius-sm);color:var(--muted);box-shadow:inset 0 0 0 1px rgba(255,255,255,.06)}
.discord-modal-backdrop{position:fixed;inset:0;background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;z-index:9000}
.discord-modal{background:var(--surface-1, #1c1c22);border:1px solid var(--accent, #5865F2);border-radius:10px;padding:20px;width:min(520px, 92vw);box-shadow:0 8px 40px rgba(0,0,0,.5)}
.discord-modal .form-label{font-size:13px;margin-bottom:4px;display:block}
.discord-modal .form-control{width:100%;padding:6px 10px;border-radius:6px;border:1px solid var(--accent);background:var(--surface-2, #111);color:var(--text, #eee)}
.text-success{color:#4ade80;font-size:13px}
.text-danger{color:#f87171;font-size:13px}
.text-muted{color:#9ca3af;font-size:12px}
</style>
