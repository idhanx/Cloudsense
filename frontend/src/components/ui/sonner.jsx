import { useTheme } from "next-themes";
import { Toaster as SonnerToaster, toast } from "sonner";

const Toaster = ({ ...props }) => {
  const { theme = "system" } = useTheme();
  return (
    <SonnerToaster 
      theme={theme} 
      {...props}
    />
  );
};

export { Toaster, toast };
