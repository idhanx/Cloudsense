"""
Temporal TCC Tracking Module

Tracks Tropical Cloud Clusters (TCCs) across consecutive time steps using
centroid proximity matching. Assigns stable track IDs to linked detections
for lifecycle analysis.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional
import numpy as np
import logging

logger = logging.getLogger(__name__)


@dataclass
class Track:
    """Represents a temporal track of TCC detections."""
    track_id: str
    detections: List[Dict] = field(default_factory=list)
    last_centroid_lat: float = 0.0
    last_centroid_lon: float = 0.0
    last_timestamp: Optional[datetime] = None
    is_active: bool = True



class TemporalTracker:
    """
    Tracks TCC detections across consecutive time steps using centroid proximity.
    
    Attributes:
        proximity_threshold_km: Maximum distance for linking (default 500 km)
        active_tracks: Dict[str, Track] of currently active tracks
        next_track_id: Counter for generating unique track IDs
    """
    
    def __init__(self, proximity_threshold_km: float = 500.0):
        """Initialize tracker with proximity threshold."""
        self.proximity_threshold_km = proximity_threshold_km
        self.active_tracks: Dict[str, Track] = {}
        self.next_track_id = 1
        logger.info(f"TemporalTracker initialized (proximity threshold: {proximity_threshold_km} km)")
    
    @staticmethod
    def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate Haversine distance between two lat/lon points in km.
        
        Args:
            lat1, lon1: First point coordinates
            lat2, lon2: Second point coordinates
        
        Returns:
            Distance in kilometers
        """
        import math
        R = 6371.0  # Earth radius in km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat/2)**2 + 
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * 
             math.sin(dlon/2)**2)
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    def _create_new_track(self, timestamp: datetime) -> str:
        """
        Generate new unique track ID.
        
        Args:
            timestamp: Current timestamp for track ID generation
        
        Returns:
            Track ID in format: "TRK_{YYYYMMDD}_{HHMM}_{counter}"
        """
        timestamp_str = timestamp.strftime("%Y%m%d_%H%M")
        track_id = f"TRK_{timestamp_str}_{self.next_track_id:03d}"
        self.next_track_id += 1
        return track_id

    
    def _find_closest_track(self, lat: float, lon: float) -> Optional[str]:
        """
        Find closest active track within proximity threshold.
        
        Args:
            lat, lon: Detection centroid coordinates
        
        Returns:
            Track ID if found within threshold, None otherwise
        """
        closest_track_id = None
        min_distance = float('inf')
        
        for track_id, track in self.active_tracks.items():
            if not track.is_active:
                continue
            
            distance = self._haversine_km(
                lat, lon,
                track.last_centroid_lat, track.last_centroid_lon
            )
            
            if distance < self.proximity_threshold_km and distance < min_distance:
                min_distance = distance
                closest_track_id = track_id
        
        return closest_track_id
    
    def update(self, detections: List[Dict], timestamp: datetime) -> List[Dict]:
        """
        Process detections for a new time step and assign track IDs.
        
        Args:
            detections: List of detection dicts with centroid_lat, centroid_lon
            timestamp: Timestamp of this detection batch
        
        Returns:
            Same detections list with track_id field added to each detection
        
        Algorithm:
            1. For each detection:
                a. Find closest active track within 500 km
                b. If found: assign to that track, update track centroid
                c. If not found: create new track
            2. Mark tracks with no match as inactive
            3. Return detections with track_id populated
        """
        if not detections:
            # Mark all tracks as inactive if no detections
            for track in self.active_tracks.values():
                track.is_active = False
            return detections
        
        # Track which tracks were matched in this timestep
        matched_tracks = set()
        
        # Process each detection
        for detection in detections:
            lat = detection['centroid_lat']
            lon = detection['centroid_lon']
            
            # Find closest track
            track_id = self._find_closest_track(lat, lon)
            
            if track_id:
                # Assign to existing track
                track = self.active_tracks[track_id]
                track.detections.append(detection)
                track.last_centroid_lat = lat
                track.last_centroid_lon = lon
                track.last_timestamp = timestamp
                matched_tracks.add(track_id)
                
                detection['track_id'] = track_id
                logger.debug(f"  Linked detection to track {track_id}")
            else:
                # Create new track
                new_track_id = self._create_new_track(timestamp)
                new_track = Track(
                    track_id=new_track_id,
                    detections=[detection],
                    last_centroid_lat=lat,
                    last_centroid_lon=lon,
                    last_timestamp=timestamp,
                    is_active=True
                )
                self.active_tracks[new_track_id] = new_track
                matched_tracks.add(new_track_id)
                
                detection['track_id'] = new_track_id
                logger.debug(f"  Created new track {new_track_id}")
        
        # Mark unmatched tracks as inactive
        for track_id, track in self.active_tracks.items():
            if track_id not in matched_tracks:
                track.is_active = False
                logger.debug(f"  Track {track_id} marked inactive (no match)")
        
        logger.info(f"Temporal tracking: {len(detections)} detections, "
                    f"{len(matched_tracks)} active tracks, "
                    f"{len(self.active_tracks) - len(matched_tracks)} inactive tracks")
        
        return detections

    
    def get_active_tracks(self) -> Dict[str, Track]:
        """
        Return currently active tracks.
        
        Returns:
            Dictionary of active tracks (track_id -> Track)
        """
        return {tid: track for tid, track in self.active_tracks.items() if track.is_active}
