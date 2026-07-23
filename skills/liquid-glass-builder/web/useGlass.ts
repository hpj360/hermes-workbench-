import { useEffect, useRef, useState } from 'react';

export interface UseGlassOptions {
  /** 基础 blur 值（px） */
  baseBlur?: number;
  /** 滚动距离阈值（px），超过后达到最大 blur */
  maxBlurAt?: number;
  /** 最大 blur 值（px） */
  maxBlur?: number;
  /** 是否启用 */
  enabled?: boolean;
}

export interface UseGlassReturn {
  blur: number;
  alpha: number;
  ref: React.RefObject<HTMLElement>;
}

/**
 * useGlass - 滚动驱动玻璃效果
 *
 * 元素从屏幕底部进入时 blur 从 0 升到 baseBlur，
 * 滚动越深 blur 越接近 maxBlur。
 *
 * @example
 * const { blur, alpha, ref } = useGlass({ baseBlur: 20, maxBlur: 40 });
 * <div ref={ref} style={{ backdropFilter: `blur(${blur}px)`, background: `rgba(255,255,255,${alpha})` }} />
 */
export function useGlass({
  baseBlur = 20,
  maxBlurAt = 200,
  maxBlur = 40,
  enabled = true,
}: UseGlassOptions = {}): UseGlassReturn {
  const ref = useRef<HTMLElement>(null);
  const [blur, setBlur] = useState(baseBlur);
  const [alpha, setAlpha] = useState(0.5);

  useEffect(() => {
    if (!enabled) return;
    const el = ref.current;
    if (!el) return;

    const handleScroll = () => {
      const rect = el.getBoundingClientRect();
      const viewportHeight = window.innerHeight;

      // 进入动画：从屏幕底部进入时 blur 0 -> baseBlur
      const enterProgress = Math.max(0, Math.min(1,
        (viewportHeight - rect.top) / viewportHeight
      ));
      const enterBlur = baseBlur * enterProgress;

      // 滚动驱动：根据内容滚动距离调整
      const scrollProgress = Math.max(0, Math.min(1,
        -rect.top / maxBlurAt
      ));
      const scrollBlur = (maxBlur - baseBlur) * scrollProgress;

      setBlur(enterBlur + scrollBlur);
      setAlpha(0.4 + 0.3 * scrollProgress);
    };

    handleScroll();
    window.addEventListener('scroll', handleScroll, { passive: true });
    window.addEventListener('resize', handleScroll);

    return () => {
      window.removeEventListener('scroll', handleScroll);
      window.removeEventListener('resize', handleScroll);
    };
  }, [baseBlur, maxBlur, maxBlurAt, enabled]);

  return { blur, alpha, ref };
}

export default useGlass;
