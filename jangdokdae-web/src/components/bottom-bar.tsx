export function BottomBar({
  children,
  caption,
}: {
  children: React.ReactNode;
  caption?: string;
}) {
  return (
    <div className="bottom-bar">
      {children}
      {caption && <p className="bottom-bar__caption">{caption}</p>}
    </div>
  );
}
