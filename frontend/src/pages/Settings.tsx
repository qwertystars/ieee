import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import {
  User,
  Building2,
  Brain,
  Plug,
  Save,
  Shield,
  Bell,
  Eye,
  EyeOff,
  Upload,
  TestTube,
  Key,
  Smartphone,
  Lock,
  Fingerprint,
  Monitor,
  Moon,
  Globe,
  Loader2,
  CheckCircle2,
  XCircle,
  Plus,
  Trash2,
  Mail,
  MessageSquare,
  AlertCircle,
} from 'lucide-react'

const TABS = [
  { key: 'profile', label: 'Profile', icon: User },
  { key: 'organization', label: 'Organization', icon: Building2 },
  { key: 'ai', label: 'AI', icon: Brain },
  { key: 'integrations', label: 'Integrations', icon: Plug },
  { key: 'security', label: 'Security', icon: Shield },
  { key: 'notifications', label: 'Notifications', icon: Bell },
] as const

type TabKey = (typeof TABS)[number]['key']

export default function Settings() {
  const { user } = useAuth()
  const [activeTab, setActiveTab] = useState<TabKey>('profile')
  const [saved, setSaved] = useState<string | null>(null)

  const [profile, setProfile] = useState({
    name: user?.name ?? '',
    email: user?.email ?? '',
    role: user?.role ?? '',
    currentPassword: '',
    newPassword: '',
    confirmPassword: '',
    timezone: 'UTC',
    language: 'en',
    theme: 'dark',
  })

  const [showCurrentPw, setShowCurrentPw] = useState(false)
  const [showNewPw, setShowNewPw] = useState(false)
  const [testStatus, setTestStatus] = useState<Record<string, 'testing' | 'success' | 'error' | null>>({})

  // TODO: no backend settings endpoint — all write features are stubbed/disabled below.

  const handleSave = (section: string) => {
    // TODO: no backend settings endpoint
    setSaved(section)
    setTimeout(() => setSaved(null), 2000)
  }

  function testConnection(key: string) {
    // TODO: no backend settings endpoint — connection tests are stubbed.
    setTestStatus((prev) => ({ ...prev, [key]: 'testing' }))
    setTimeout(() => {
      setTestStatus((prev) => ({ ...prev, [key]: 'error' }))
      setTimeout(() => setTestStatus((prev) => ({ ...prev, [key]: null })), 3000)
    }, 1500)
  }

  function TestButton({ label, testKey }: { label: string; testKey: string }) {
    const status = testStatus[testKey]
    return (
      <button
        onClick={() => testConnection(testKey)}
        disabled={status === 'testing'}
        className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 rounded text-xs text-slate-300 transition-colors disabled:opacity-50"
      >
        {status === 'testing' ? (
          <><Loader2 size={12} className="animate-spin" /> Testing...</>
        ) : status === 'success' ? (
          <><CheckCircle2 size={12} className="text-green-400" /> Connected</>
        ) : status === 'error' ? (
          <><XCircle size={12} className="text-red-400" /> Failed</>
        ) : (
          <><TestTube size={12} /> {label}</>
        )}
      </button>
    )
  }

  function FeatureUnavailable() {
    return (
      <div className="flex items-start gap-3 p-4 mb-4 bg-yellow-900/20 border border-yellow-700/50 rounded-lg">
        <AlertCircle size={18} className="text-yellow-500 flex-shrink-0 mt-0.5" />
        <div>
          <p className="text-sm font-medium text-yellow-500">Feature not available</p>
          <p className="text-xs text-slate-400 mt-0.5">
            Settings management is not backed by the current API. Read-only user information is shown below.
          </p>
        </div>
      </div>
    )
  }

  function ReadOnlyBadge() {
    return <span className="text-[10px] px-1.5 py-0.5 bg-slate-700 text-slate-400 rounded">Read-only</span>
  }

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6">Settings</h1>

      <div className="flex gap-1 border-b border-slate-800 mb-6 overflow-x-auto">
        {TABS.map((tab) => {
          const Icon = tab.icon
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                activeTab === tab.key
                  ? 'border-red-500 text-white'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              <Icon size={16} />
              {tab.label}
            </button>
          )
        })}
      </div>

      {activeTab === 'profile' && (
        <div className="max-w-2xl space-y-4">
          <FeatureUnavailable />
          <div className="bg-slate-900 rounded-lg border border-slate-800 p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Profile Settings</h2>
              <ReadOnlyBadge />
            </div>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Name</label>
                  <input
                    value={profile.name}
                    onChange={(e) => setProfile({ ...profile, name: e.target.value })}
                    disabled
                    className="w-full px-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-slate-500 cursor-not-allowed"
                  />
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Email</label>
                  <input
                    type="email"
                    value={profile.email}
                    onChange={(e) => setProfile({ ...profile, email: e.target.value })}
                    disabled
                    className="w-full px-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-slate-500 cursor-not-allowed"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">Role</label>
                <input
                  value={profile.role}
                  disabled
                  className="w-full px-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-slate-500 cursor-not-allowed"
                />
              </div>
              {user && (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2 border-t border-slate-800">
                  <div>
                    <label className="block text-xs text-slate-500 mb-1">Organization</label>
                    <p className="text-sm text-slate-300">{user.organization ?? '—'}</p>
                  </div>
                  <div>
                    <label className="block text-xs text-slate-500 mb-1">Phone</label>
                    <p className="text-sm text-slate-300">{user.phone ?? '—'}</p>
                  </div>
                  <div>
                    <label className="block text-xs text-slate-500 mb-1">Status</label>
                    <p className="text-sm text-slate-300 capitalize">{user.status}</p>
                  </div>
                </div>
              )}
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Timezone</label>
                  <select value={profile.timezone} disabled className="w-full px-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-slate-500 cursor-not-allowed">
                    <option value="UTC">UTC</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Language</label>
                  <select value={profile.language} disabled className="w-full px-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-slate-500 cursor-not-allowed">
                    <option value="en">English</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Theme</label>
                  <select value={profile.theme} disabled className="w-full px-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-slate-500 cursor-not-allowed">
                    <option value="dark">Dark</option>
                  </select>
                </div>
              </div>
            </div>
            <div className="mt-6 flex items-center gap-3">
              <button
                onClick={() => handleSave('profile')}
                disabled
                className="flex items-center gap-2 px-4 py-2 bg-red-600/50 rounded-lg text-white text-sm cursor-not-allowed"
              >
                <Save size={16} /> Save Changes
              </button>
              {saved === 'profile' && <span className="text-green-400 text-sm">Saved!</span>}
            </div>
          </div>

          <div className="bg-slate-900 rounded-lg border border-slate-800 p-6">
            <h2 className="text-lg font-semibold mb-4">Change Password</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1">Current Password</label>
                <div className="relative">
                  <input
                    type={showCurrentPw ? 'text' : 'password'}
                    value={profile.currentPassword}
                    onChange={(e) => setProfile({ ...profile, currentPassword: e.target.value })}
                    disabled
                    className="w-full px-3 py-2 pr-10 bg-slate-800/50 border border-slate-700 rounded-lg text-slate-500 cursor-not-allowed"
                  />
                  <button type="button" onClick={() => setShowCurrentPw(!showCurrentPw)} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
                    {showCurrentPw ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">New Password</label>
                  <div className="relative">
                    <input
                      type={showNewPw ? 'text' : 'password'}
                      value={profile.newPassword}
                      onChange={(e) => setProfile({ ...profile, newPassword: e.target.value })}
                      disabled
                      className="w-full px-3 py-2 pr-10 bg-slate-800/50 border border-slate-700 rounded-lg text-slate-500 cursor-not-allowed"
                    />
                    <button type="button" onClick={() => setShowNewPw(!showNewPw)} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
                      {showNewPw ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Confirm Password</label>
                  <input
                    type="password"
                    value={profile.confirmPassword}
                    onChange={(e) => setProfile({ ...profile, confirmPassword: e.target.value })}
                    disabled
                    className="w-full px-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-slate-500 cursor-not-allowed"
                  />
                </div>
              </div>
              <button
                onClick={() => handleSave('password')}
                disabled
                className="flex items-center gap-2 px-4 py-2 bg-red-600/50 rounded-lg text-white text-sm cursor-not-allowed"
              >
                <Lock size={16} /> Update Password
              </button>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'organization' && (
        <div className="max-w-2xl space-y-4">
          <FeatureUnavailable />
          <div className="bg-slate-900 rounded-lg border border-slate-800 p-6">
            <h2 className="text-lg font-semibold mb-4">Organization Settings</h2>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Organization Name</label>
                  <input value="" disabled placeholder="Enter organization name" className="w-full px-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-slate-500 cursor-not-allowed" />
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Organization Type</label>
                  <select disabled className="w-full px-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-slate-500 cursor-not-allowed">
                    <option value="">Select type</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">Region</label>
                <input value="" disabled placeholder="e.g. South Asia, West Africa" className="w-full px-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-slate-500 cursor-not-allowed" />
              </div>
            </div>
            <div className="mt-6 flex items-center gap-3">
              <button onClick={() => handleSave('organization')} disabled className="flex items-center gap-2 px-4 py-2 bg-red-600/50 rounded-lg text-white text-sm cursor-not-allowed">
                <Save size={16} /> Save Changes
              </button>
              {saved === 'organization' && <span className="text-green-400 text-sm">Saved!</span>}
            </div>
          </div>

          <div className="bg-slate-900 rounded-lg border border-slate-800 p-6">
            <h2 className="text-lg font-semibold mb-4">Branding</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-2">Logo</label>
                <div className="flex items-center gap-4">
                  <div className="w-16 h-16 bg-slate-800 rounded-lg border border-slate-700 flex items-center justify-center">
                    <Upload size={20} className="text-slate-500" />
                  </div>
                  <button disabled className="px-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-sm text-slate-500 cursor-not-allowed">
                    Upload Logo
                  </button>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Primary Color</label>
                  <div className="flex items-center gap-2">
                    <input type="color" value="#dc2626" disabled className="w-10 h-10 rounded cursor-not-allowed bg-transparent opacity-50" />
                    <input value="#dc2626" disabled className="flex-1 px-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-slate-500 cursor-not-allowed font-mono text-sm" />
                  </div>
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Secondary Color</label>
                  <div className="flex items-center gap-2">
                    <input type="color" value="#1e293b" disabled className="w-10 h-10 rounded cursor-not-allowed bg-transparent opacity-50" />
                    <input value="#1e293b" disabled className="flex-1 px-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-slate-500 cursor-not-allowed font-mono text-sm" />
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-slate-900 rounded-lg border border-slate-800 p-6">
            <h2 className="text-lg font-semibold mb-4">Labels Configuration</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-2">Severity Levels</label>
                <div className="flex flex-wrap gap-2">
                  {['low', 'medium', 'high', 'critical'].map((level) => (
                    <span key={level} className="px-3 py-1 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-300 capitalize">{level}</span>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-2">Disaster Types</label>
                <div className="flex flex-wrap gap-2">
                  {['flood', 'earthquake', 'fire', 'hurricane'].map((type) => (
                    <span key={type} className="px-3 py-1 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-300 capitalize">{type}</span>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-2">Status Labels</label>
                <div className="flex flex-wrap gap-2">
                  {['active', 'monitoring', 'resolved', 'archived'].map((label) => (
                    <span key={label} className="px-3 py-1 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-300 capitalize">{label}</span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'ai' && (
        <div className="max-w-2xl space-y-4">
          <FeatureUnavailable />
          <div className="bg-slate-900 rounded-lg border border-slate-800 p-6">
            <h2 className="text-lg font-semibold mb-4">AI Provider Configuration</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1">Base URL</label>
                <input value="" disabled placeholder="https://api.openai.com/v1" className="w-full px-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-slate-500 cursor-not-allowed" />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">API Key</label>
                <input type="password" value="" disabled placeholder="sk-..." className="w-full px-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-slate-500 cursor-not-allowed" />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Model</label>
                  <select disabled className="w-full px-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-slate-500 cursor-not-allowed">
                    <option value="gpt-4">GPT-4</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Monthly Budget Limit ($)</label>
                  <input type="number" value="100" disabled className="w-full px-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-slate-500 cursor-not-allowed" />
                </div>
              </div>
              <div className="flex items-center gap-3">
                <TestButton label="Test Connection" testKey="ai" />
                <label className="flex items-center gap-2 cursor-not-allowed opacity-50">
                  <input type="checkbox" checked disabled className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-red-500" />
                  <span className="text-sm text-slate-300">Safe Mode</span>
                </label>
              </div>
            </div>
          </div>

          <div className="bg-slate-900 rounded-lg border border-slate-800 p-6">
            <h2 className="text-lg font-semibold mb-4">AI Features</h2>
            <div className="space-y-3">
              {([
                { key: 'autoClassify' as const, label: 'Auto-classify incidents', desc: 'Automatically classify incident type and severity using AI' },
                { key: 'autoEscalate' as const, label: 'Auto-escalation', desc: 'Automatically escalate incidents based on AI risk assessment' },
                { key: 'suggestResources' as const, label: 'Resource suggestions', desc: 'AI-powered resource allocation recommendations' },
                { key: 'briefingEnabled' as const, label: 'AI Briefings', desc: 'Generate automated situation briefings' },
              ]).map((opt) => (
                <label key={opt.key} className="flex items-start gap-3 p-3 bg-slate-800 rounded-lg cursor-not-allowed opacity-60">
                  <input type="checkbox" checked={false} disabled className="mt-1 w-4 h-4 rounded border-slate-600 bg-slate-800 text-red-500" />
                  <div>
                    <p className="text-sm font-medium text-slate-200">{opt.label}</p>
                    <p className="text-xs text-slate-500">{opt.desc}</p>
                  </div>
                </label>
              ))}
            </div>
            <div className="mt-6 flex items-center gap-3">
              <button onClick={() => handleSave('ai')} disabled className="flex items-center gap-2 px-4 py-2 bg-red-600/50 rounded-lg text-white text-sm cursor-not-allowed">
                <Save size={16} /> Save Changes
              </button>
              {saved === 'ai' && <span className="text-green-400 text-sm">Saved!</span>}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'integrations' && (
        <div className="max-w-2xl space-y-4">
          <FeatureUnavailable />
          {[
            { key: 'sms', label: 'SMS Provider', icon: Smartphone, options: [{ value: 'twilio', label: 'Twilio' }] },
            { key: 'email', label: 'Email Provider', icon: Mail, options: [{ value: 'sendgrid', label: 'SendGrid' }] },
            { key: 'whatsapp', label: 'WhatsApp Provider', icon: MessageSquare, options: [{ value: 'twilio', label: 'Twilio' }] },
            { key: 'push', label: 'Push Notifications', icon: Bell, options: [{ value: 'firebase', label: 'Firebase' }] },
          ].map((integration) => {
            const Icon = integration.icon
            return (
              <div key={integration.key} className="bg-slate-900 rounded-lg border border-slate-800 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-semibold flex items-center gap-2"><Icon size={18} /> {integration.label}</h2>
                  <TestButton label="Test" testKey={integration.key} />
                </div>
                <div className="space-y-3">
                  <div>
                    <label className="block text-sm text-slate-400 mb-1">Provider</label>
                    <select disabled className="w-full px-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-slate-500 cursor-not-allowed">
                      <option value="">Select provider</option>
                      {integration.options.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm text-slate-400 mb-1">API Key</label>
                    <input type="password" value="" disabled placeholder="Enter API key" className="w-full px-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-slate-500 cursor-not-allowed" />
                  </div>
                </div>
              </div>
            )
          })}
          <div className="flex items-center gap-3">
            <button onClick={() => handleSave('integrations')} disabled className="flex items-center gap-2 px-4 py-2 bg-red-600/50 rounded-lg text-white text-sm cursor-not-allowed">
              <Save size={16} /> Save All Integrations
            </button>
            {saved === 'integrations' && <span className="text-green-400 text-sm">Saved!</span>}
          </div>
        </div>
      )}

      {activeTab === 'security' && (
        <div className="max-w-2xl space-y-4">
          <FeatureUnavailable />
          <div className="bg-slate-900 rounded-lg border border-slate-800 p-6">
            <h2 className="text-lg font-semibold mb-4">Multi-Factor Authentication</h2>
            <div className="space-y-4">
              <label className="flex items-center justify-between p-4 bg-slate-800 rounded-lg cursor-not-allowed opacity-60">
                <div className="flex items-center gap-3">
                  <Smartphone size={20} className="text-blue-400" />
                  <div>
                    <p className="text-sm font-medium text-slate-200">Authenticator App</p>
                    <p className="text-xs text-slate-500">Use an authenticator app for 2FA</p>
                  </div>
                </div>
                <button disabled className="px-3 py-1.5 rounded text-xs font-medium bg-slate-700 text-slate-400 cursor-not-allowed">
                  Enable
                </button>
              </label>
              <label className="flex items-center justify-between p-4 bg-slate-800 rounded-lg cursor-not-allowed opacity-60">
                <div className="flex items-center gap-3">
                  <Fingerprint size={20} className="text-purple-400" />
                  <div>
                    <p className="text-sm font-medium text-slate-200">Passkey</p>
                    <p className="text-xs text-slate-500">Use biometrics or security key</p>
                  </div>
                </div>
                <button disabled className="px-3 py-1.5 rounded text-xs font-medium bg-slate-700 text-slate-400 cursor-not-allowed">
                  Register
                </button>
              </label>
            </div>
          </div>

          <div className="bg-slate-900 rounded-lg border border-slate-800 p-6">
            <h2 className="text-lg font-semibold mb-4">Active Sessions</h2>
            <div className="space-y-3">
              {[{ id: '1', device: 'Current browser', ip: '—', lastActive: 'Just now', current: true }].map((session) => (
                <div key={session.id} className="flex items-center justify-between p-3 bg-slate-800 rounded-lg">
                  <div className="flex items-center gap-3">
                    <Monitor size={18} className="text-slate-400" />
                    <div>
                      <p className="text-sm font-medium text-slate-200">{session.device}</p>
                      <p className="text-xs text-slate-500">{session.ip} • {session.lastActive}</p>
                    </div>
                  </div>
                  <span className="text-xs text-green-400 px-2 py-1 bg-green-500/10 rounded">Current</span>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-slate-900 rounded-lg border border-slate-800 p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">API Keys</h2>
              <button disabled className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800/50 border border-slate-700 rounded text-sm text-slate-500 cursor-not-allowed">
                <Plus size={14} /> Generate Key
              </button>
            </div>
            <div className="space-y-3">
              {[{ id: '1', name: 'No keys configured', key: '—', created: '—', lastUsed: '—' }].map((apiKey) => (
                <div key={apiKey.id} className="flex items-center justify-between p-3 bg-slate-800 rounded-lg">
                  <div className="flex items-center gap-3">
                    <Key size={18} className="text-yellow-400" />
                    <div>
                      <p className="text-sm font-medium text-slate-200">{apiKey.name}</p>
                      <p className="text-xs text-slate-500 font-mono">{apiKey.key} • Last used: {apiKey.lastUsed}</p>
                    </div>
                  </div>
                  <button disabled className="p-1.5 text-slate-500 cursor-not-allowed">
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'notifications' && (
        <div className="max-w-2xl space-y-4">
          <FeatureUnavailable />
          <div className="bg-slate-900 rounded-lg border border-slate-800 p-6">
            <h2 className="text-lg font-semibold mb-4">Channel Preferences</h2>
            <div className="space-y-3">
              {[
                { key: 'smsEnabled' as const, label: 'SMS', icon: Smartphone, desc: 'Receive alerts via SMS' },
                { key: 'emailEnabled' as const, label: 'Email', icon: Mail, desc: 'Receive alerts via email' },
                { key: 'pushEnabled' as const, label: 'Push Notifications', icon: Bell, desc: 'Browser and mobile push notifications' },
                { key: 'whatsappEnabled' as const, label: 'WhatsApp', icon: MessageSquare, desc: 'Receive alerts via WhatsApp' },
              ].map((ch) => {
                const Icon = ch.icon
                return (
                  <label key={ch.key} className="flex items-center justify-between p-3 bg-slate-800 rounded-lg cursor-not-allowed opacity-60">
                    <div className="flex items-center gap-3">
                      <Icon size={18} className="text-slate-400" />
                      <div>
                        <p className="text-sm font-medium text-slate-200">{ch.label}</p>
                        <p className="text-xs text-slate-500">{ch.desc}</p>
                      </div>
                    </div>
                    <input type="checkbox" checked={false} disabled className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-red-500" />
                  </label>
                )
              })}
            </div>
          </div>

          <div className="bg-slate-900 rounded-lg border border-slate-800 p-6">
            <h2 className="text-lg font-semibold mb-4">Notification Types</h2>
            <div className="space-y-3">
              {[
                { key: 'incidentAlerts' as const, label: 'Incident Alerts', desc: 'New incidents and severity changes' },
                { key: 'taskUpdates' as const, label: 'Task Updates', desc: 'Task assignments and status changes' },
                { key: 'shelterAlerts' as const, label: 'Shelter Alerts', desc: 'Capacity warnings and status changes' },
                { key: 'systemAlerts' as const, label: 'System Alerts', desc: 'System maintenance and updates' },
              ].map((nt) => (
                <label key={nt.key} className="flex items-center justify-between p-3 bg-slate-800 rounded-lg cursor-not-allowed opacity-60">
                  <div>
                    <p className="text-sm font-medium text-slate-200">{nt.label}</p>
                    <p className="text-xs text-slate-500">{nt.desc}</p>
                  </div>
                  <input type="checkbox" checked={false} disabled className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-red-500" />
                </label>
              ))}
            </div>
          </div>

          <div className="bg-slate-900 rounded-lg border border-slate-800 p-6">
            <h2 className="text-lg font-semibold mb-4">Quiet Hours</h2>
            <label className="flex items-center justify-between mb-4 cursor-not-allowed opacity-60">
              <div>
                <p className="text-sm font-medium text-slate-200">Enable Quiet Hours</p>
                <p className="text-xs text-slate-500">Suppress non-critical notifications during these hours</p>
              </div>
              <input type="checkbox" checked={false} disabled className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-red-500" />
            </label>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1">Start</label>
                <input type="time" value="22:00" disabled className="w-full px-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-slate-500 cursor-not-allowed" />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">End</label>
                <input type="time" value="07:00" disabled className="w-full px-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-slate-500 cursor-not-allowed" />
              </div>
            </div>
            <div className="mt-4 flex items-center gap-3">
              <button onClick={() => handleSave('notifications')} disabled className="flex items-center gap-2 px-4 py-2 bg-red-600/50 rounded-lg text-white text-sm cursor-not-allowed">
                <Save size={16} /> Save Changes
              </button>
              {saved === 'notifications' && <span className="text-green-400 text-sm">Saved!</span>}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
