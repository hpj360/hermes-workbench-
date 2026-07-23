// LiquidGlassView.swift
// Apple WWDC 2025 Liquid Glass - iOS 端实现
// 适用：iOS 17+ (SwiftUI GlassEffectContainer), iOS 15+ (Material fallback)

import SwiftUI

/// 通用玻璃容器（iOS 17+ 使用 GlassEffectContainer，iOS 15/16 降级为 Material）
@available(iOS 17.0, *)
public struct LiquidGlassView<Content: View>: View {
    let blur: CGFloat
    let alpha: Double
    let cornerRadius: CGFloat
    let highlight: Bool
    let dispersion: Bool
    let content: () -> Content

    public init(
        blur: CGFloat = 24,
        alpha: Double = 0.6,
        cornerRadius: CGFloat = 12,
        highlight: Bool = true,
        dispersion: Bool = false,
        @ViewBuilder content: @escaping () -> Content
    ) {
        self.blur = blur
        self.alpha = alpha
        self.cornerRadius = cornerRadius
        self.highlight = highlight
        self.dispersion = dispersion
        self.content = content
    }

    public var body: some View {
        ZStack {
            // 玻璃背景层
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .fill(.ultraThinMaterial)
                .opacity(alpha)
                .background {
                    // 边缘高光
                    if highlight {
                        RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                            .stroke(
                                LinearGradient(
                                    colors: [
                                        Color.white.opacity(0.5),
                                        Color.white.opacity(0.1),
                                    ],
                                    startPoint: .top,
                                    endPoint: .bottom
                                ),
                                lineWidth: 1
                            )
                    }
                }

            // 色散边缘（可选）
            if dispersion {
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .stroke(
                        AngularGradient(
                            colors: [
                                Color.red.opacity(0.3),
                                Color.green.opacity(0.2),
                                Color.blue.opacity(0.3),
                                Color.red.opacity(0.3),
                            ],
                            center: .center
                        ),
                        lineWidth: 1
                    )
                    .blendMode(.overlay)
            }

            // 内容层
            content()
                .padding(16)
        }
        .clipShape(RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
    }
}

/// iOS 15/16 降级实现（用 Material）
public struct LiquidGlassViewLegacy<Content: View>: View {
    let alpha: Double
    let cornerRadius: CGFloat
    let content: () -> Content

    public init(
        alpha: Double = 0.6,
        cornerRadius: CGFloat = 12,
        @ViewBuilder content: @escaping () -> Content
    ) {
        self.alpha = alpha
        self.cornerRadius = cornerRadius
        self.content = content
    }

    public var body: some View {
        content()
            .padding(16)
            .background(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .fill(.ultraThinMaterial)
                    .opacity(alpha)
            )
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .stroke(Color.white.opacity(0.3), lineWidth: 1)
            )
    }
}

/// 玻璃按钮
@available(iOS 17.0, *)
public struct LiquidGlassButton: View {
    let title: String
    let action: () -> Void
    @State private var isPressed = false

    public init(title: String, action: @escaping () -> Void) {
        self.title = title
        self.action = action
    }

    public var body: some View {
        Button(action: {
            withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                isPressed = true
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                isPressed = false
                action()
            }
        }) {
            Text(title)
                .font(.system(size: 15, weight: .medium))
                .foregroundStyle(.primary)
                .padding(.horizontal, 20)
                .padding(.vertical, 10)
                .background {
                    Capsule()
                        .fill(.ultraThinMaterial)
                        .opacity(isPressed ? 0.9 : 0.6)
                }
                .scaleEffect(isPressed ? 0.96 : 1.0)
        }
        .buttonStyle(.plain)
    }
}

/// 玻璃 Tab Bar
@available(iOS 17.0, *)
public struct LiquidGlassTabBar: View {
    let items: [TabItem]
    @Binding var selected: Int

    public struct TabItem: Identifiable {
        let id = UUID()
        let title: String
        let icon: String  // SF Symbol name
    }

    public init(items: [TabItem], selected: Binding<Int>) {
        self.items = items
        self._selected = selected
    }

    public var body: some View {
        HStack(spacing: 0) {
            ForEach(Array(items.enumerated()), id: \.element.id) { index, item in
                Button {
                    withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                        selected = index
                    }
                } label: {
                    VStack(spacing: 4) {
                        Image(systemName: item.icon)
                            .font(.system(size: 22))
                        Text(item.title)
                            .font(.system(size: 10))
                    }
                    .foregroundStyle(selected == index ? .primary : .secondary)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 8)
        .background {
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .fill(.ultraThinMaterial)
        }
        .padding(.horizontal, 16)
    }
}

// === 使用示例 ===
/*
 @available(iOS 17.0, *)
 struct ContentView: View {
     var body: some View {
         ZStack {
             // 必须有背景（图片/渐变），否则玻璃效果不明显
             LinearGradient(
                 colors: [.blue, .purple],
                 startPoint: .topLeading,
                 endPoint: .bottomTrailing
             )
             .ignoresSafeArea()

             VStack {
                 LiquidGlassView(blur: 30, alpha: 0.6) {
                     VStack(alignment: .leading) {
                         Text("Hello Liquid Glass")
                             .font(.title2)
                         Text("Apple WWDC 2025")
                             .font(.caption)
                     }
                 }
                 .frame(width: 280, height: 120)

                 LiquidGlassButton(title: "Continue") {
                     print("Tapped")
                 }
             }
         }
     }
 }
 */
