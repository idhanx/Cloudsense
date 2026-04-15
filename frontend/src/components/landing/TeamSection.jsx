import { Github, Linkedin, Mail } from 'lucide-react';

const team = [
    {
        name: 'Dhanush',
        role: 'Developer',
        description: 'Full Stack & AI Engineer',
    },
    {
        name: 'Asita',
        role: 'Developer',
        description: 'Full Stack & AI Engineer',
    },
    {
        name: 'Akshaya',
        role: 'Developer',
        description: 'Full Stack & AI Engineer',
    },
];

const TeamSection = () => {
    return (
        <section className="py-20 bg-gray-900 border-t border-gray-800">
            <div className="max-w-7xl mx-auto px-4">
                <div className="text-center mb-16">
                    <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">
                        Meet the Team
                    </h2>
                    <p className="text-xl text-gray-400 max-w-2xl mx-auto">
                        The minds behind CloudSense
                    </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-5xl mx-auto">
                    {team.map((member, index) => (
                        <div
                            key={index}
                            className="bg-gray-800/50 rounded-xl p-8 border border-gray-700 hover:border-cyan-400/50 transition-all hover:transform hover:-translate-y-1 text-center group"
                        >
                            <div className="w-24 h-24 bg-gradient-to-br from-cyan-500 to-blue-600 rounded-full mx-auto mb-6 flex items-center justify-center text-3xl font-bold text-white shadow-lg group-hover:shadow-cyan-500/25 transition-shadow">
                                {member.name[0]}
                            </div>

                            <h3 className="text-xl font-bold text-white mb-1">{member.name}</h3>
                            <p className="text-cyan-400 font-medium mb-3">{member.role}</p>
                            <p className="text-gray-400 mb-6 text-sm">{member.description}</p>
                        </div>
                    ))}
                </div>
            </div>
        </section>
    );
};

export default TeamSection;
