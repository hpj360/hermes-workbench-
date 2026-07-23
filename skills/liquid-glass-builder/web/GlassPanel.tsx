import React, { CSSProperties, ElementType, ReactNode } from 'react';
import './liquid-glass.css';

export interface GlassPanelProps {
  /** 模糊半径 px，默认 24 */
  blur?: number;
  /** 背景透明度 0-1，默认 0.6 */
  alpha?: number;
  /** 是否显示 1px 高光边框，默认 true */
  border?: boolean;
  /** 是否显示顶部高光，默认 false */
  highlight?: boolean;
  /** 是否添加色散边缘，默认 false */
  dispersion?: boolean;
  /** 主题，默认 auto */
  variant?: 'light' | 'dark' | 'auto';
  /** 圆角 px，默认 12 */
  radius?: number;
  /** 渲染元素，默认 div */
  as?: ElementType;
  /** 子内容 */
  children?: ReactNode;
  /** 自定义 className */
  className?: string;
  /** 自定义 style */
  style?: CSSProperties;
}

/**
 * Liquid Glass 通用面板
 *
 * @example
 * <GlassPanel blur={24} alpha={0.6} highlight>
 *   <h2>Title</h2>
 * </GlassPanel>
 */
export function GlassPanel({
  blur = 24,
  alpha,
  border = true,
  highlight = false,
  dispersion = false,
  variant = 'auto',
  radius = 12,
  as: Component = 'div',
  children,
  className = '',
  style,
}: GlassPanelProps) {
  const computedStyle: CSSProperties = {
    backdropFilter: `blur(${blur}px)`,
    WebkitBackdropFilter: `blur(${blur}px)`,
    borderRadius: radius,
    ...(alpha !== undefined && {
      background: variant === 'dark'
        ? `rgba(20, 20, 20, ${alpha})`
        : `rgba(255, 255, 255, ${alpha})`,
    }),
    ...(border === false && { border: 'none' }),
    ...style,
  };

  const classes = [
    'glass',
    highlight && 'glass-highlight',
    dispersion && 'glass-dispersion',
    className,
  ].filter(Boolean).join(' ');

  return (
    <Component className={classes} style={computedStyle}>
      {children}
    </Component>
  );
}

/**
 * Liquid Glass 按钮
 */
export interface GlassButtonProps extends GlassPanelProps {
  onClick?: () => void;
  disabled?: boolean;
  type?: 'button' | 'submit' | 'reset';
  size?: 'sm' | 'md' | 'lg';
}

export function GlassButton({
  onClick,
  disabled = false,
  type = 'button',
  size = 'md',
  children,
  ...rest
}: GlassButtonProps) {
  const sizeMap = { sm: 32, md: 40, lg: 48 };
  const padMap = { sm: '4px 12px', md: '8px 16px', lg: '12px 24px' };

  return (
    <GlassPanel
      as="button"
      onClick={disabled ? undefined : onClick}
      radius={sizeMap[size] / 2}
      style={{
        height: sizeMap[size],
        padding: padMap[size],
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.5 : 1,
        border: 'none',
        fontSize: size === 'sm' ? 13 : size === 'md' ? 15 : 17,
        fontWeight: 500,
        ...rest.style,
      }}
      {...rest}
    >
      {children}
    </GlassPanel>
  );
}

export default GlassPanel;
