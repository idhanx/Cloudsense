import { useState } from 'react';
import { Play, Pause, SkipBack, SkipForward } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';

const TimelineSlider = () => {
  const [currentFrame, setCurrentFrame] = useState(24);
  const [isPlaying, setIsPlaying] = useState(false);
  const totalFrames = 48;

  const formatTime = (frame) => {
    const hours = Math.floor((frame * 30) / 60);
    const minutes = (frame * 30) % 60;
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')} UTC`;
  };

  return (
    <div className="bg-card rounded-lg p-6 border border-border h-full">
      <h3 className="text-lg font-semibold mb-4">Temporal Navigation</h3>

      <div className="text-3xl font-mono text-center mb-6">
        {formatTime(currentFrame)}
      </div>

      <div className="flex items-center justify-center gap-2 mb-6">
        <Button
          variant="outline"
          size="icon"
          onClick={() => setCurrentFrame(0)}
        >
          <SkipBack className="w-4 h-4" />
        </Button>
        <Button
          variant="default"
          size="icon"
          onClick={() => setIsPlaying(!isPlaying)}
        >
          {isPlaying ? (
            <Pause className="w-4 h-4" />
          ) : (
            <Play className="w-4 h-4" />
          )}
        </Button>
        <Button
          variant="outline"
          size="icon"
          onClick={() => setCurrentFrame(totalFrames)}
        >
          <SkipForward className="w-4 h-4" />
        </Button>
      </div>

      <Slider
        value={[currentFrame]}
        onValueChange={(v) => setCurrentFrame(v[0])}
        max={totalFrames}
        min={0}
        step={1}
        className="cursor-pointer mb-4"
      />

      <div className="flex justify-between text-xs text-muted-foreground mb-6">
        <span>0</span>
        <span>24</span>
        <span>48</span>
      </div>

      <div className="grid grid-cols-4 gap-2 text-center text-xs">
        <div className="bg-muted rounded py-1">00:00</div>
        <div className="bg-muted rounded py-1">06:00</div>
        <div className="bg-muted rounded py-1">12:00</div>
        <div className="bg-muted rounded py-1">18:00</div>
      </div>
    </div>
  );
};

export default TimelineSlider;

