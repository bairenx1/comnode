import React from 'react';
import { AppMode, Theme } from '../types';
import { Image as ImageIcon, ImagePlus, Video, Users, Shirt, Paintbrush, Library, BookOpen, Settings, Zap, Palette } from 'lucide-react';

interface Props {
  currentMode: AppMode;
  onSelectMode: (mode: AppMode) => void;
  currentTheme: Theme;
  onChangeTheme: (theme: Theme) => void;
}

export function Sidebar({ currentMode, onSelectMode, currentTheme, onChangeTheme }: Props) {
  const topItems: { id: AppMode; label: string; icon: React.ElementType }[] = [
    { id: 't2i', label: '文生图', icon: ImageIcon },
    { id: 'i2i', label: '图生图', icon: ImagePlus },
    { id: 'i2v', label: '图生视频', icon: Video },
    { id: 'face', label: '模特换脸', icon: Users },
    { id: 'clothes', label: '电商换衣', icon: Shirt },
    { id: 'inpaint', label: '局部重绘', icon: Paintbrush },
  ];

  const bottomItems: { id: AppMode; label: string; icon: React.ElementType }[] = [
    { id: 'assets', label: '资产库', icon: Library },
    { id: 'prompts', label: '提示词库', icon: BookOpen },
    { id: 'settings', label: '设置', icon: Settings },
  ];

  const NavButton = ({ item }: { item: typeof topItems[0] }) => {
    const isActive = currentMode === item.id;
    const Icon = item.icon;
    return (
      <button
        onClick={() => onSelectMode(item.id)}
        className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-all duration-200 border ${
          isActive
            ? 'bg-accent/10 text-accent border-accent/20 shadow-[inset_0_0_20px_var(--theme-accent)]'
            : 'text-text-secondary hover:bg-bg-input hover:text-text-primary border-transparent'
        }`}
      >
        <Icon className={`w-5 h-5 ${isActive ? 'text-accent' : 'text-text-secondary'}`} />
        {item.label}
      </button>
    );
  };

  const themes: { id: Theme; label: string }[] = [
    { id: 'midnight', label: '暗夜' },
    { id: 'cyberpunk', label: '赛博' },
    { id: 'minimal', label: '极简' },
    { id: 'vaporwave', label: '蒸汽' },
  ];

  return (
    <div className="h-full w-full bg-bg-base border-r border-border-main flex flex-col">
      {/* Logo */}
      <div className="h-14 lg:h-16 flex items-center justify-between px-6 border-b border-border-main shrink-0 select-none">
        <div className="flex items-center gap-2 text-text-primary font-bold text-lg tracking-wide">
          <div className="p-1.5 bg-accent text-accent-text rounded-md shadow-[0_0_15px_var(--theme-accent)]">
             <Zap className="w-5 h-5 fill-current" />
          </div>
          NODE<span className="font-light text-text-secondary">STUDIO</span>
        </div>
      </div>

      {/* Top Menu */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-3 py-6 space-y-1">
         <div className="text-[10px] font-mono text-text-secondary uppercase tracking-widest pl-3 mb-4">工作流模块</div>
         {topItems.map((item) => <NavButton key={item.id} item={item} />)}
      </div>

      {/* Bottom Menu & Theme Switcher */}
      <div className="px-3 py-4 border-t border-border-main space-y-1 bg-bg-base">
         <div className="px-3 pb-3 mb-3 border-b border-border-main/50">
           <div className="flex items-center gap-2 text-[10px] font-mono text-text-secondary uppercase tracking-widest mb-2">
             <Palette className="w-3 h-3" /> 主题风格
           </div>
           <div className="flex gap-1.5 flex-wrap">
             {themes.map((t) => (
               <button
                 key={t.id}
                 onClick={() => onChangeTheme(t.id)}
                 className={`text-[10px] px-2 py-1 rounded transition-colors ${
                   currentTheme === t.id 
                     ? 'bg-accent text-accent-text' 
                     : 'bg-bg-input text-text-secondary hover:text-text-primary'
                 }`}
               >
                 {t.label}
               </button>
             ))}
           </div>
         </div>
         {bottomItems.map((item) => <NavButton key={item.id} item={item} />)}
      </div>
    </div>
  );
}
