import HeroSection from '@/components/landing/HeroSection';
import FeaturesSection from '@/components/landing/FeaturesSection';
import AboutSection from '@/components/landing/AboutSection';
import Footer from '@/components/landing/Footer';
import AnimatedBackground from '@/components/landing/AnimatedBackground';

const Landing = () => {
  return (
    <div className="relative bg-[#0B0F1A] text-white">
      {/* Fixed canvas background — stays behind everything */}
      <AnimatedBackground />

      {/* Scrollable content — all above the canvas */}
      <div className="relative z-10">
        <HeroSection />
        <FeaturesSection />
        <AboutSection />
        <Footer />
      </div>
    </div>
  );
};

export default Landing;
