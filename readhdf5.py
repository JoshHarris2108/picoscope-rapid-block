import h5py
import matplotlib.pyplot as plt

def read_hdf5(filename):
  """
    Function to print and check all the metadata is present and to loop through the channels in a 
    given hdf5 file, and plot the first capture in each channel as well as plotting the PHA of the entire channel
  """
  with h5py.File(filename,'r') as f:
      metadata = {}

      metadata_group = f['metadata']

      for key in metadata_group.attrs:
        metadata[key] = metadata_group.attrs[key]
        print(metadata[key])

      for ch in range(len(metadata['active_channels'])):
        counts = f['adc_counts_'+str((metadata['active_channels'])[ch])]
        pha = f['pha_'+str((metadata['active_channels'])[ch])]

        plt.plot(counts[0][:])
        plt.show()

        plt.plot(pha[0], pha[1], 'bo-')
        plt.show()

        # Checks the shape of the output data is as expected.
        print(f'counts shape{counts.shape}, pha shape{pha.shape}')



read_hdf5("/tmp/pico_captures/2023-06-12_10:44:59.084709.hdf5")
