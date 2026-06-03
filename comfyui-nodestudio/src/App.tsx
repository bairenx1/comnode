import { useState, useEffect } from 'react';
import { Sidebar } from './components/Sidebar';
import { Workspace } from './components/Workspace';
import { AppMode, Theme } from './types';
import { Menu, X, ExternalLink } from 'lucide-react';

export default function App() {
  const [mode, setMode] = useState<AppMode>('t2i');
  const [theme, setTheme] = useState<Theme>('midnight');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [pendingImageUrl, setPendingImageUrl] = useState<string | null>(null);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  const handleSendToWorkflow = (newMode: AppMode, imageUrl?: string) => {
    setMode(newMode);
    setPendingImageUrl(imageUrl || null);
  };

  return (
    <div className="flex h-screen w-full bg-bg-base text-text-primary overflow-hidden font-sans">
      {/* Mobile Overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/60 z-40 lg:hidden backdrop-blur-sm transition-opacity"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar Navigation */}
      <div
        className={`fixed inset-y-0 left-0 z-50 w-64 transform transition-transform duration-300 ease-in-out lg:relative lg:translate-x-0 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        } shadow-2xl lg:shadow-none`}
      >
         {/* Close button for mobile */}
         <button 
           className="lg:hidden absolute top-4 right-4 text-text-secondary hover:text-text-primary z-50 bg-bg-panel rounded p-1"
           onClick={() => setSidebarOpen(false)}
         >
           <X className="w-5 h-5" />
         </button>
         
        <Sidebar 
           currentMode={mode} 
           onSelectMode={(m) => { setMode(m); setSidebarOpen(false); }} 
           currentTheme={theme}
           onChangeTheme={setTheme}
        />
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 h-full relative z-0">
         {/* Mobile Header */}
         <div className="lg:hidden flex items-center h-14 border-b border-border-main bg-bg-base px-4 shrink-0 shadow-sm z-30">
            <button 
               onClick={() => setSidebarOpen(true)} 
               className="text-text-secondary hover:text-text-primary transition-colors"
            >
               <Menu className="w-6 h-6" />
            </button>
            <div className="ml-4 font-semibold text-text-primary flex items-center gap-2 text-sm tracking-wide flex-1">
               <div className="w-2 h-2 rounded-full bg-accent animate-pulseglow shadow-[0_0_8px_var(--theme-accent)]"></div>
               NODE ENGINE
            </div>
            <a
              href="http://127.0.0.1:8188"
              target="_blank"
              rel="noopener noreferrer"
              className="text-[11px] font-mono flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-border-main/60 bg-accent/10 hover:bg-accent/20 text-accent hover:text-accent transition-all"
            >
              <ExternalLink className="w-3 h-3" />
              ComfyUI
            </a>
         </div>

         {/* Top bar for desktop */}
         <div className="hidden lg:flex items-center justify-end h-10 px-5 border-b border-border-main/50 bg-bg-panel/60 shrink-0">
            <a
              href="http://127.0.0.1:8188"
              target="_blank"
              rel="noopener noreferrer"
              className="text-[11px] font-mono flex items-center gap-1.5 px-3 py-1 rounded-md border border-border-main/60 bg-accent/10 hover:bg-accent/20 text-accent hover:text-accent transition-all"
            >
              <ExternalLink className="w-3 h-3" />
              ComfyUI 原生画布
            </a>
         </div>
         {/* Active Workspace View */}
         <Workspace mode={mode} onSendToWorkflow={handleSendToWorkflow} pendingImageUrl={pendingImageUrl} onClearPendingImage={() => setPendingImageUrl(null)} />
      </div>
    </div>
  );
}
