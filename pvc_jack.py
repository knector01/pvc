import threading
import tkinter

import numpy as np
import jack

import pvc

class CircularBuffer:
    def __init__(self, n):
        self.arr = np.zeros(n)
        self.widx = 0
        self.ridx = 0
        
    def peek(self, n, offset=0):
        start = (self.ridx + offset) % self.arr.size
        end = start + n
        
        if end > self.arr.size:
            l_start = start
            l_end = self.arr.size
            r_start = 0
            r_end = end - self.arr.size
            
            split = l_end - l_start
            
            out = np.zeros(n)
            
            out[:split] = self.arr[l_start:l_end]
            out[split:] = self.arr[r_start:r_end]
            
            return out
        else:
            return self.arr[start:end]
        
    def write(self, data, offset=0):
        n = data.size
        
        start = (self.widx + offset) % self.arr.size
        end = start + n
        
        if end > self.arr.size:
            l_start = start
            l_end = self.arr.size
            r_start = 0
            r_end = end - self.arr.size
            
            split = l_end - l_start
            
            self.arr[l_start:l_end] = data[:split] 
            self.arr[r_start:r_end] = data[split:]
        else:
            self.arr[start:end] = data
            
    def write_add(self, data, offset=0):
        n = data.size
        
        start = (self.widx + offset) % self.arr.size
        end = start + n
        
        if end > self.arr.size:
            l_start = start
            l_end = self.arr.size
            r_start = 0
            r_end = end - self.arr.size
            
            split = l_end - l_start
            
            self.arr[l_start:l_end] += data[:split] 
            self.arr[r_start:r_end] += data[split:]
        else:
            self.arr[start:end] += data
        
    def radvance(self, n):
        self.ridx = (self.ridx + n) % self.arr.size
        
    def wadvance(self, n):
        self.widx = (self.widx + n) % self.arr.size
        
    def get_unread(self):
        n = self.widx - self.ridx
        if n < 0:
            n += self.arr.size
        return n
        

class PVCJack:
    def __init__(self):
        self.client = jack.Client("PVCJack")
        self.client.inports.register("input")
        self.client.outports.register("output")
        self.event = threading.Event()
        self.window_size = 4096
        self.n_windows = 4
        
        self.gain = 2

        self.inbuffer = CircularBuffer(self.window_size * 2)
        self.outbuffer = CircularBuffer(self.window_size * 2)
        # NOTE: this might not work when window size isn't even multiple of JACK block size
        self.outbuffer.widx = self.outbuffer.arr.size // 2

        self.pvc = pvc.PitchShifter(self.client.samplerate, self.window_size, 1, 1, True, 8)
        
        self.client.set_process_callback(self.process)
        self.client.set_shutdown_callback(self.shutdown)

    def process(self, frames):
        assert frames == self.client.blocksize
        data = self.client.inports[0].get_array()
        self.inbuffer.write(data)
        self.inbuffer.wadvance(frames)

        while self.inbuffer.get_unread() >= self.window_size:
            advance = self.window_size // self.n_windows

            block = self.inbuffer.peek(self.window_size)

            out_block = self.pvc.process(block, advance, advance)

            self.outbuffer.write(np.zeros(advance), advance * (self.n_windows - 1))
            self.outbuffer.write_add(out_block)
                
            self.inbuffer.radvance(advance)
            self.outbuffer.wadvance(advance)

        self.client.outports[0].get_array()[:] = self.outbuffer.peek(frames) * self.gain
        self.outbuffer.radvance(frames)

    def shutdown(self, status, reason):
        print("JACK shutdown!")
        print("status:", status)
        print("reason:", reason)
        self.event.set()

    def run(self):
        with self.client:
            try:
                self.event.wait()
            except KeyboardInterrupt:
                print("Interrupted by user")

class GUI:
    def __init__(self, pvc_jack):
        self.sliders = []
        self.labels = []
        self.pvc_jack = pvc_jack
        
        self.tk = tkinter.Tk()
        self.tk.title("PVCJack")
        
        self.tk.columnconfigure(1,weight=1)
        
        self.create_slider(self.set_pitch, "pitch")
        self.create_slider(self.set_formant, "formant")
        
    def set_pitch(self, x):
        self.pvc_jack.pvc.pitch_mult = float(x)
    
    def set_formant(self, x):
        self.pvc_jack.pvc.f_pitch_mult = float(x)
        
    def create_slider(self,cmd,name):
        i = len(self.sliders)
        
        label = tkinter.Label(self.tk, text=name)
        self.labels.append(label)
        label.grid(row=i,column=0,sticky="SE")
        
        slider = tkinter.Scale(self.tk, from_=0.1, to=4, resolution=0.01, orient=tkinter.HORIZONTAL, command=cmd)
        slider.set(1)
        self.sliders.append(slider)
        slider.grid(row=i,column=1,sticky="EW")

if __name__ == "__main__":
    pvc_jack = PVCJack()
    gui = GUI(pvc_jack)
    #pvc_jack.run()
    with pvc_jack.client:
        gui.tk.mainloop()